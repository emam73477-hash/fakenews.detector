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
app.secret_key = os.environ.get("SECRET_KEY", "pro_secret_key_123")

# ==========================================
# 🔑 الإعدادات والمفاتيح
# ==========================================
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") 
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")
DB_FILE = "local_db.json"

# المصادر الموثوقة ومدققي الحقائق
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "aljazeera.net", "alarabiya.net", "youm7.com", 
    "skynewsarabia.com", "masrawy.com", "rt.com", "cnn.com", "apnews.com", 
    "kooora.com", "yallakora.com", "filgoal.com", "al-ain.com"
]
FACT_CHECKERS = ["misbar.com", "fatabyyano.net", "dabegad.com", "snopes.com", "politifact.com"]

# ==========================================
# 🗄️ إدارة قاعدة البيانات (JSON)
# ==========================================
def load_db():
    if not os.path.exists(DB_FILE): return {"users": [], "history": [], "reports": []}
    try: 
        with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"users": [], "history": [], "reports": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(username):
    db = load_db()
    return next((u for u in db['users'] if u['username'] == username), None)

# ==========================================
# 📧 نظام التنبيهات البريدية (Brevo)
# ==========================================
def send_email_otp(receiver_email, otp):
    # نفس دالة الإرسال الأصلية للأكواد
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": "Detector App", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "Verification Code",
        "htmlContent": f"<h1>{otp}</h1>"
    }
    requests.post(url, headers=headers, json=payload)

def send_admin_alert(news_text, verdict):
    """إضافة جديدة: تنبيه للمسؤول عند رصد خبر كاذب خطير"""
    if not BREVO_API_KEY: return
    headers = {"api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": "AI ALERT", "email": SENDER_EMAIL},
        "to": [{"email": SENDER_EMAIL}],
        "subject": "⚠️ إشاعة قوية مرصودة",
        "htmlContent": f"<p>تم فحص خبر وحصل على نتيجة ({verdict}):</p><b>{news_text}</b>"
    }
    requests.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=payload)

# ==========================================
# 🧠 المحرك المطور (تحليل زمني، تناقض، وعناوين مضللة)
# ==========================================
def analyze_news_logic(text, lang="ar"):
    url = "https://google.serper.dev/search"
    today = datetime.datetime.now()
    
    # 1. تحليل الوقت (أمس/اليوم)
    tbs = "qdr:w" # أسبوع افتراضياً
    if any(word in text for word in ["أمس", "اليوم", "today", "yesterday"]): tbs = "qdr:d2"

    # 2. الكلمات المناقضة (فوز ضد خسارة)
    opposites = {"خسارة": ["فوز", "فاز"], "وفاة": ["بصحة", "ينفي", "إشاعة"], "loss": ["win"], "death": ["alive"]}
    negation_signals = ["خدعة", "كذب", "إشاعة", "نفت", "fake", "rumor", "hoax"]

    # البحث المزدوج
    query = f"حقيقة {text}" if lang == "ar" else f"truth about {text}"
    payload = {"q": query, "gl": "eg" if lang=="ar" else "us", "hl": lang, "num": 10, "tbs": tbs}
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        organic = res.json().get("organic", [])
        if not organic: return {"verdict": "غير مؤكد", "score": 50, "reasons": ["لا نتائج"]}

        score = 50
        is_fake = False
        reasons = []

        for item in organic:
            content = (item.get("title", "") + " " + item.get("snippet", "")).lower()
            link = item.get("link", "").lower()

            # كشف العناوين المضللة (مثل: خدعة وفاة..)
            if any(sig in content for sig in negation_signals):
                if any(ts in link for ts in TRUSTED_SOURCES + FACT_CHECKERS):
                    is_fake = True
                    reasons.append(f"تم كشفها كإشاعة في {link.split('/')[2]}")

            # كشف التناقض
            for k, v in opposites.items():
                if k in text and any(w in content for w in v):
                    is_fake = True
                    reasons.append(f"تضارب: المصادر تذكر {v[0]}")

        verdict = "❌ خبر كاذب" if is_fake else ("✅ خبر صادق" if score > 60 else "⚠️ مضلل/غير مؤكد")
        return {
            "verdict": verdict, "score": 15 if is_fake else 85,
            "reasons": list(set(reasons)), "sources": [{"title": r['title'], "link": r['link']} for r in organic[:3]]
        }
    except: return {"verdict": "خطأ اتصال", "score": 0}

# ==========================================
# 🆕 الإضافات الجديدة (Modules)
# ==========================================

def save_history(username, text, verdict):
    """إضافة: سجل البحث"""
    db = load_db()
    db['history'].append({"user": username, "query": text, "verdict": verdict, "date": str(datetime.datetime.now())})
    save_db(db)

@app.route('/report-error', methods=['POST'])
def report_error():
    """إضافة: نظام التبليغ"""
    data = request.get_json()
    db = load_db()
    db['reports'].append({**data, "date": str(datetime.datetime.now())})
    save_db(db)
    return jsonify({"status": "ok"})

@app.route('/check-source', methods=['POST'])
def check_source():
    """إضافة: فحص موثوقية الرابط"""
    url = request.get_json().get('url', '').lower()
    res = "غير مدرج"
    if any(s in url for s in TRUSTED_SOURCES): res = "مصدر موثوق ✅"
    elif any(s in url for s in FACT_CHECKERS): res = "مدقق حقائق 🔍"
    return jsonify({"result": res})

@app.route('/trending')
def trending():
    """إضافة: الأخبار الزائفة الرائجة"""
    db = load_db()
    fakes = [h for h in db['history'] if "كاذب" in h['verdict']]
    return jsonify(fakes[-5:])

# ==========================================
# 🌐 المسارات الأصلية (Routes)
# ==========================================

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    text, lang = data.get('text', ''), data.get('lang', 'ar')
    
    # فلترة الكلمات والرموز
    if len(re.findall(r'\w+', text)) < 3: return jsonify({"error": "أدخل 3 كلمات"}), 400

    result = analyze_news_logic(text, lang)
    save_history(session['user'], text, result['verdict']) # حفظ السجل
    
    if result['score'] < 30: # تنبيه للمسؤول إذا الخبر كاذب جداً
        threading.Thread(target=send_admin_alert, args=(text, result['verdict'])).start()
        
    return jsonify(result)

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

# (تكملة مسارات register و logout تبقى كما هي في كودك الأصلي)

if __name__ == '__main__':
    app.run(debug=True, port=5000)


