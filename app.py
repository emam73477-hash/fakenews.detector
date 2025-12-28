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

# ==========================================
# 🌍 Trusted Sources & Fact Checkers
# ==========================================
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com",
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com", 
    "masrawy.com", "shorouknews.com", "independentarabia.com", "bbc.com/arabic"
]

FACT_CHECKERS = [
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org",
    "fatabyyano.net", "misbar.com", "dabegad.com"
]

# ==========================================
# 🗄️ Database Helpers
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE): return {"users": [], "news": []}
    try: 
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {"users": [], "news": []}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

def get_user(username):
    db = load_db()
    for user in db['users']:
        if user['username'] == username: return user
    return None

def create_user(user_data):
    db = load_db()
    if any(u['username'] == user_data['username'] for u in db['users']): return False
    user_data['created_at'] = str(datetime.datetime.now())
    db['users'].append(user_data)
    save_db(db)
    return True

# ==========================================
# 🧠 AI Core: News Analysis Logic
# ==========================================
def analyze_news_logic(text, lang="en"):
    url = "https://google.serper.dev/search"
    
    # 1. الاعدادات بناءً على اللغة
    if lang == 'ar':
        payload = json.dumps({"q": text, "gl": "eg", "hl": "ar"})
        labels = {
            "real": "✅ خبر حقيقي", "fake": "❌ خبر زائف", "unsure": "⚠️ غير مؤكد",
            "date_lbl": "أقدم ظهور تقريبي: ", "no_res": "لم يتم العثور على مصادر كافية.",
            "trusted_lbl": "مصدر موثوق: ", "fact_lbl": "تحقيق من: ",
            "fake_words": ["كاذب", "زائف", "شائعة", "غير صحيح", "مفبرك", "إشاعة", "تضليل"]
        }
    else:
        payload = json.dumps({"q": text, "gl": "us", "hl": "en"})
        labels = {
            "real": "✅ REAL", "fake": "❌ FAKE", "unsure": "⚠️ UNVERIFIED",
            "date_lbl": "Earliest appearance: ", "no_res": "No sufficient sources found.",
            "trusted_lbl": "Trusted Source: ", "fact_lbl": "Fact Check: ",
            "fake_words": ["false", "fake", "hoax", "scam", "myth", "debunked", "misleading"]
        }

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        organic_results = data.get("organic", [])
        
        if not organic_results:
            return {"verdict": labels["unsure"], "score": 0, "reasons": [labels["no_res"]], "sources": []}

        score = 50
        found_sources = []
        reasons = []
        all_dates = []

        for result in organic_results:
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            date_str = result.get("date")

            if date_str: all_dates.append(date_str)

            # مراجعة مدققي الحقائق (تأثير قوي جداً)
            for checker in FACT_CHECKERS:
                if checker in link:
                    found_sources.append({"title": result['title'], "link": result['link'], "type": "Fact Checker"})
                    if any(word in title or word in snippet for word in labels["fake_words"]):
                        score -= 50
                        reasons.append(f"{labels['fact_lbl']} {checker} ({labels['fake']})")
                    else:
                        score += 30 # إذا ذكرته مواقع الحقيقة بدون كلمات سلبية قد يكون حقيقي

            # مراجعة المصادر الموثوقة
            for trusted in TRUSTED_SOURCES:
                if trusted in link:
                    score += 25
                    reasons.append(f"{labels['trusted_lbl']} {trusted}")
                    found_sources.append({"title": result['title'], "link": result['link'], "type": "Trusted"})

        # تحديد أقدم تاريخ
        # ملاحظة: Serper يعطي التواريخ بتنسيقات مختلفة، سنعرض أول تاريخ يجده البحث كأقدم ظهور
        earliest_date = all_dates[-1] if all_dates else "Unknown"
        date_info = f"{labels['date_lbl']} {earliest_date}"

        # النتيجة النهائية
        if score >= 75: verdict = labels["real"]
        elif score <= 35: verdict = labels["fake"]
        else: verdict = labels["unsure"]

        return {
            "verdict": verdict,
            "score": max(0, min(score, 100)),
            "date_info": date_info,
            "reasons": list(set(reasons[:3])),
            "sources": found_sources[:5]
        }

    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "reasons": [str(e)], "sources": []}

# ==========================================
# 🌐 Routes
# ==========================================
@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    news_text = data.get('text', '').strip()
    lang = data.get('lang', 'en')

    # --- 1. التحقق من عدد الكلمات (أكثر من 3 كلمات) ---
    # استخدام regex لاستخراج الكلمات فقط وتجاهل الرموز
    words = re.findall(r'\w+', news_text) 
    
    if len(words) < 3:
        error_msg = "Please enter at least 3 meaningful words." if lang == 'en' else "يرجى إدخال 3 كلمات مفهومة على الأقل."
        return jsonify({"error": error_msg}), 400

    # --- 2. التحقق من وجود حروف (ليست مجرد رموز) ---
    if not any(c.isalpha() for c in news_text):
        error_msg = "Input must contain actual words, not just symbols." if lang == 'en' else "يجب أن يحتوي النص على كلمات وليس رموزاً فقط."
        return jsonify({"error": error_msg}), 400

    result = analyze_news_logic(news_text, lang)
    return jsonify(result)

# (بقية المسارات: login, register, verify_otp تبقى كما هي في الكود الأصلي)
@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid Login")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)


