import os
import json
import random
import datetime
import threading
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "competition_secret")

# ==========================================
# 🔑 API KEYS
# ==========================================
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") 
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")

TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com",
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com", 
    "masrawy.com", "shorouknews.com", "independentarabia.com", "bbc.com/arabic",
    "al-ain.com", "kooora.com", "yallakora.com"
]

FACT_CHECKERS = ["snopes.com", "politifact.com", "factcheck.org", "fullfact.org", "fatabyyano.net", "misbar.com", "dabegad.com"]

# ==========================================
# 🗄️ Database Helpers
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE): return {"users": [], "news": [], "history": [], "reports": []}
    try: 
        with open(DB_FILE, 'r', encoding='utf-8') as f: 
            data = json.load(f)
            for key in ["history", "reports"]:
                if key not in data: data[key] = []
            return data
    except: return {"users": [], "news": [], "history": [], "reports": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(username):
    db = load_db()
    return next((u for u in db['users'] if u['username'] == username), None)

def create_user(user_data):
    db = load_db()
    if any(u['username'] == user_data['username'] for u in db['users']): return False
    user_data['created_at'] = str(datetime.datetime.now())
    db['users'].append(user_data)
    save_db(db)
    return True

# ==========================================
# 📧 Email & Alerts
# ==========================================
def send_email_logic(receiver_email, otp):
    if not SENDER_EMAIL or not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {"sender": {"name": "Detector", "email": SENDER_EMAIL}, "to": [{"email": receiver_email}], "subject": "OTP", "htmlContent": f"<h1>{otp}</h1>"}
    try: requests.post(url, headers=headers, json=payload, timeout=10)
    except: pass

def send_admin_alert(news_text, verdict):
    if not SENDER_EMAIL or not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {"sender": {"name": "AI Alert", "email": SENDER_EMAIL}, "to": [{"email": SENDER_EMAIL}], "subject": "⚠️ Fake News Alert", "htmlContent": f"<p>News: {news_text}<br>Verdict: {verdict}</p>"}
    try: requests.post(url, headers=headers, json=payload, timeout=10)
    except: pass

# ==========================================
# 🧠 AI Core: الذكاء المطور للتعامل مع الوقت والتاريخ
# ==========================================
def analyze_news_logic(text, lang="en"):
    url = "https://google.serper.dev/search"
    now = datetime.datetime.now()
    
    # 🕒 1. معالجة البعد الزمني (أمس، اليوم، الآن)
    tbs_param = "" 
    time_sensitive = False
    
    if lang == 'ar':
        search_query = f"{text} حقيقة"
        LBL_REAL, LBL_FAKE, LBL_UNSURE = "خبر حقيقي", "خبر زائف", "غير مؤكد"
        NEGATIONS = ["خدعة", "كذب", "إشاعة", "نفي", "مفبرك", "غير صحيح", "شائعة"]
        # إذا وجد كلمات زمنية، نحدد البحث لآخر 48 ساعة لضمان عدم جلب أخبار قديمة
        if any(w in text for w in ["أمس", "امس", "اليوم", "ساعة", "دقيقة", "عاجل"]):
            tbs_param = "qdr:d2" # نتائج آخر يومين فقط
            time_sensitive = True
    else:
        search_query = f"{text} truth"
        LBL_REAL, LBL_FAKE, LBL_UNSURE = "REAL", "FAKE", "UNVERIFIED"
        NEGATIONS = ["hoax", "fake", "rumor", "denied", "false", "debunked"]
        if any(w in text.lower() for w in ["yesterday", "today", "now", "recent", "urgent"]):
            tbs_param = "qdr:d2"
            time_sensitive = True

    payload = {"q": search_query, "gl": "eg" if lang == 'ar' else "us", "hl": lang}
    if tbs_param:
        payload["tbs"] = tbs_param # إضافة فلتر الوقت

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        organic_results = data.get("organic", [])
        
        if not organic_results:
            return {"verdict": LBL_UNSURE, "score": 50, "reasons": ["لم نجد نتائج حديثة لهذا الخبر"], "sources": []}

        score = 50
        reasons = []
        found_sources = []
        is_fake_confirmed = False
        captured_dates = []

        for result in organic_results:
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            date_str = result.get("date", "")
            if date_str: captured_dates.append(date_str)

            content = title + " " + snippet
            
            # أ- كشف التكذيب في المصادر الموثوقة
            has_negation = any(word in content for word in NEGATIONS)
            is_trusted = any(ts in link for ts in TRUSTED_SOURCES)
            is_checker = any(fc in link for fc in FACT_CHECKERS)

            if has_negation:
                if is_trusted or is_checker:
                    is_fake_confirmed = True
                    reasons.append(f"تم كشف الخبر كإشاعة في: {link.split('/')[2]}")
                score -= 30
            elif is_trusted:
                score += 20
                reasons.append(f"تأكيد من مصدر موثوق: {link.split('/')[2]}")
                found_sources.append({"title": result.get("title"), "link": link})

        # ب- الحسم النهائي
        if is_fake_confirmed:
            verdict, score = LBL_FAKE, 15
        elif score >= 80:
            verdict = LBL_REAL
        elif score <= 35:
            verdict = LBL_FAKE
        else:
            verdict = LBL_UNSURE

        # ج- تصحيح التاريخ: عرض أحدث تاريخ وجدناه
        display_date = captured_dates[0] if captured_dates else "N/A"

        return {
            "verdict": verdict,
            "score": max(0, min(score, 100)),
            "date_info": f"أحدث ظهور مرصود: {display_date}" if time_sensitive else f"أول ظهور للخبر: {display_date}",
            "reasons": list(set(reasons))[:2],
            "sources": found_sources[:5]
        }
    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "reasons": [str(e)], "sources": []}

# ==========================================
# 🆕 New Modules & Routes
# ==========================================
def save_to_history(username, text, result):
    db = load_db()
    db['history'].append({"user": username, "query": text, "verdict": result['verdict'], "timestamp": str(datetime.datetime.now())})
    save_db(db)

@app.route('/report-error', methods=['POST'])
def report_error():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    db = load_db()
    db['reports'].append({**data, "user": session['user'], "timestamp": str(datetime.datetime.now())})
    save_db(db)
    return jsonify({"message": "Success"})

@app.route('/check-source', methods=['POST'])
def check_source():
    data = request.get_json()
    url = data.get('url', '').lower()
    if any(s in url for s in TRUSTED_SOURCES): status = "Trusted Source ✅"
    elif any(s in url for s in FACT_CHECKERS): status = "Fact Checker 🔍"
    else: status = "Unknown Source ⚠️"
    return jsonify({"status": status})

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    news_text = data.get('text', '').strip()
    lang = data.get('lang', 'ar')
    
    words = re.findall(r'\w+', news_text)
    if len(words) < 3: return jsonify({"error": "Please enter at least 3 words."}), 400
        
    result = analyze_news_logic(news_text, lang)
    save_to_history(session['user'], news_text, result)
    
    if result['score'] < 30:
        threading.Thread(target=send_admin_alert, args=(news_text, result['verdict'])).start()
    return jsonify(result)

# --- Auth Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username, email, password = request.form['username'], request.form['email'], request.form['password']
        if get_user(username): return "Username exists"
        otp = str(random.randint(1000, 9999))
        threading.Thread(target=send_email_logic, args=(email, otp)).start()
        session['temp_user'] = {"username": username, "email": email, "password": generate_password_hash(password)}
        session['otp'] = otp
        return redirect(url_for('verify_otp'))
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        if request.form.get('otp') == session.get('otp'):
            create_user(session['temp_user'])
            session['user'] = session['temp_user']['username']
            session.pop('temp_user', None)
            return redirect(url_for('home'))
    return render_template('verify.html', email=session['temp_user']['email'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)




