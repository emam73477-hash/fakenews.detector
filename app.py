import os
import json
import random
import datetime
import threading
import requests
import re  # تم إضافة re للتحقق من الكلمات
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

# ==========================================
# 🌍 Trusted Sources & Fact Checkers
# ==========================================
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com",
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com", 
    "masrawy.com", "shorouknews.com", "independentarabia.com", "bbc.com/arabic",
    "al-ain.com", "kooora.com", "yallakora.com"
]

FACT_CHECKERS = [
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org",
    "fatabyyano.net", "misbar.com", "dabegad.com"
]

# ==========================================
# 🗄️ Database & Helpers (Updated for History/Reports)
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE): 
        return {"users": [], "news": [], "history": [], "reports": []}
    try: 
        with open(DB_FILE, 'r', encoding='utf-8') as f: 
            data = json.load(f)
            # التأكد من وجود المفاتيح الجديدة
            for key in ["history", "reports"]:
                if key not in data: data[key] = []
            return data
    except: return {"users": [], "news": [], "history": [], "reports": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: 
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(username):
    db = load_db()
    for user in db['users']:
        if user['username'] == username: return user
    return None

def create_user(user_data):
    db = load_db()
    for user in db['users']:
        if user['username'] == user_data['username']: return False
    user_data['created_at'] = str(datetime.datetime.now())
    db['users'].append(user_data)
    save_db(db)
    return True

# ==========================================
# 📧 Email Logic (OTP + Admin Alerts)
# ==========================================
def send_email_logic(receiver_email, otp):
    if not SENDER_EMAIL or not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": "FakeNews Detector", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "Verification Code / كود التفعيل",
        "htmlContent": f"<div style='text-align: center;'><h1>{otp}</h1></div>"
    }
    try: requests.post(url, headers=headers, json=payload, timeout=10)
    except: pass

def send_admin_alert(news_text, verdict):
    """إضافة جديدة: إرسال تنبيه للمسؤول عند رصد خبر كاذب مؤكد"""
    if not SENDER_EMAIL or not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": "System Alert", "email": SENDER_EMAIL},
        "to": [{"email": SENDER_EMAIL}],
        "subject": "⚠️ High Confidence Fake News Detected",
        "htmlContent": f"<p>AI detected a fake story: <b>{news_text}</b><br>Verdict: {verdict}</p>"
    }
    try: requests.post(url, headers=headers, json=payload, timeout=10)
    except: pass

# ==========================================
# 🧠 AI Core: Enhanced Analysis Logic
# ==========================================
def analyze_news_logic(text, lang="en"):
    url = "https://google.serper.dev/search"
    
    # تحسين البحث بإضافة كلمات حمالة للحقيقة (مثل 'حقيقة' أو 'truth')
    search_query = f"{text} حقيقة" if lang == 'ar' else f"{text} truth"
    
    if lang == 'ar':
        payload = json.dumps({"q": search_query, "gl": "eg", "hl": "ar"})
        labels = {"real": "خبر حقيقي", "fake": "خبر زائف", "unsure": "غير مؤكد", "date": "أقدم ظهور: ", "negations": ["خدعة", "كذب", "إشاعة", "نفي", "مفبرك", "غير صحيح"]}
    else:
        payload = json.dumps({"q": search_query, "gl": "us", "hl": "en"})
        labels = {"real": "REAL", "fake": "FAKE", "unsure": "UNVERIFIED", "date": "Earliest seen: ", "negations": ["hoax", "fake", "rumor", "denied", "false", "debunked"]}

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        organic_results = data.get("organic", [])
        
        if not organic_results:
            return {"verdict": labels["unsure"], "score": 0, "reasons": ["No sources found"], "sources": []}

        score = 50
        reasons = []
        found_sources = []
        is_fake_confirmed = False
        all_dates = []

        for result in organic_results:
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            date = result.get("date", "")
            if date: all_dates.append(date)

            # كشف التكذيب في العناوين (حل مشكلة خدعة موت فلان)
            found_negation = any(word in title or word in snippet for word in labels["negations"])
            
            is_trusted = any(ts in link for ts in TRUSTED_SOURCES)
            is_fact_checker = any(fc in link for fc in FACT_CHECKERS)

            if found_negation:
                if is_trusted or is_fact_checker:
                    is_fake_confirmed = True
                    reasons.append(f"Confirmed as rumor by: {link.split('/')[2]}")
                score -= 30
            elif is_trusted:
                score += 20
                reasons.append(f"Source: {link.split('/')[2]}")
                found_sources.append({"title": result.get("title"), "link": link})

        # النتيجة النهائية
        if is_fake_confirmed:
            verdict = labels["fake"]
            score = 15
        elif score >= 80:
            verdict = labels["real"]
        elif score <= 35:
            verdict = labels["fake"]
        else:
            verdict = labels["unsure"]

        earliest_date = all_dates[-1] if all_dates else "N/A"

        return {
            "verdict": verdict,
            "score": max(0, min(score, 100)),
            "date_info": f"{labels['date']}{earliest_date}",
            "reasons": list(set(reasons))[:2],
            "sources": found_sources[:5]
        }

    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "reasons": [str(e)], "sources": []}

# ==========================================
# 🆕 New Modules: History, Reports, CheckSource
# ==========================================

def save_to_history(username, text, result):
    db = load_db()
    db['history'].append({
        "user": username,
        "query": text,
        "verdict": result['verdict'],
        "timestamp": str(datetime.datetime.now())
    })
    save_db(db)

@app.route('/report-error', methods=['POST'])
def report_error():
    """إضافة: نظام التبليغ عن خطأ في النتيجة"""
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    db = load_db()
    db['reports'].append({
        "user": session['user'],
        "query": data.get('query'),
        "ai_verdict": data.get('verdict'),
        "user_correction": data.get('correction'),
        "timestamp": str(datetime.datetime.now())
    })
    save_db(db)
    return jsonify({"message": "Report received"})

@app.route('/check-source', methods=['POST'])
def check_source():
    """إضافة: فحص هل الرابط موثوق أم لا"""
    data = request.get_json()
    url = data.get('url', '').lower()
    if any(s in url for s in TRUSTED_SOURCES): status = "Trusted Source ✅"
    elif any(s in url for s in FACT_CHECKERS): status = "Fact Checker 🔍"
    else: status = "Unknown/Unverified Source ⚠️"
    return jsonify({"status": status})

@app.route('/trending')
def trending():
    """إضافة: الأخبار الزائفة المنتشرة مؤخراً"""
    db = load_db()
    fakes = [h for h in db['history'] if "زائف" in h['verdict'] or "FAKE" in h['verdict']]
    return jsonify(fakes[-5:])

# ==========================================
# 🌐 Routes
# ==========================================
@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    news_text = data.get('text', '').strip()
    lang = data.get('lang', 'ar')
    
    # --- التحقق من جودة المدخلات ---
    words = re.findall(r'\w+', news_text)
    if len(words) < 3:
        error = "Please enter at least 3 words." if lang == 'en' else "يرجى إدخال 3 كلمات مفهومة على الأقل."
        return jsonify({"error": error}), 400

    if not any(c.isalpha() for c in news_text):
        error = "Input must contain letters." if lang == 'en' else "يجب أن يحتوي النص على حروف."
        return jsonify({"error": error}), 400
        
    result = analyze_news_logic(news_text, lang)
    
    # حفظ في السجل
    save_to_history(session['user'], news_text, result)
    
    # تنبيه المسؤول إذا كان الخبر كاذباً جداً
    if result['score'] < 30:
        threading.Thread(target=send_admin_alert, args=(news_text, result['verdict'])).start()
        
    return jsonify(result)

# --- Auth Routes (تكملة الكود الأصلي) ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if get_user(username): return "Username exists"
        otp = str(random.randint(1000, 9999))
        thread = threading.Thread(target=send_email_logic, args=(email, otp))
        thread.start()
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



