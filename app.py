import os
import json
import datetime
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "super_secure_key_2025"

# ==========================================
# 🔑 الإعدادات (هام: تأكد من وضع المفتاح بشكل صحيح)
# ==========================================
SERPER_API_KEY = "YOUR_SERPER_API_KEY_HERE"  # استبدل هذا بالمفتاح الخاص بك
DB_FILE = "users_db.json"

TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "aljazeera.net", "alarabiya.net", 
    "youm7.com", "skynewsarabia.com", "masrawy.com", "rt.com",
    "cnn.com", "apnews.com", "kooora.com", "yallakora.com", "filgoal.com", "al-ain.com"
]

FACT_CHECKERS = [
    "misbar.com", "fatabyyano.net", "dabegad.com", "snopes.com"
]

# ==========================================
# 🧠 المحرك الذكي المطور (بحث مزدوج)
# ==========================================
def deep_analyze_news(text, lang="ar"):
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    # 1. إستراتيجية البحث المزدوج لضمان الحصول على نتائج
    # نجرب البحث بكلمة "حقيقة" أولاً، وإذا فشل نستخدم النص الأصلي
    queries_to_try = [f"حقيقة {text}", text] if lang == "ar" else [f"truth about {text}", text]
    
    results = []
    for q in queries_to_try:
        payload = {
            "q": q,
            "gl": "eg" if lang == "ar" else "us",
            "hl": lang,
            "num": 10
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                results = data.get("organic", [])
                if results: break # إذا وجدنا نتائج نتوقف عن المحاولة التالية
            elif response.status_code == 403:
                return {"verdict": "⚠️ خطأ في المفتاح", "score": 0, "reasons": ["مفتاح API غير صحيح أو منتهي"]}
        except:
            continue

    if not results:
        return {"verdict": "⚠️ غير مؤكد", "score": 50, "reasons": ["لم نجد نتائج بحث كافية للتحقق من هذا الخبر حالياً"]}

    # 2. تحليل المحتوى المكتشف
    score = 50 
    reasons = []
    negation_words = ["خدعة", "كذب", "إشاعة", "شائعة", "لا صحة", "نفي", "ينفي", "نفت", "مفبرك", "زيف", "fake", "hoax", "rumor"]
    
    is_fake = False
    found_trusted = False

    for res in results:
        title = res.get("title", "").lower()
        snippet = res.get("snippet", "").lower()
        content = title + " " + snippet
        link = res.get("link", "").lower()

        # كشف التكذيب
        found_negation = [w for w in negation_words if w in content]
        is_trusted = any(ts in link for ts in TRUSTED_SOURCES)
        is_fact_checker = any(fc in link for fc in FACT_CHECKERS)

        if found_negation:
            if is_trusted or is_fact_checker:
                is_fake = True
                reasons.append(f"تم كشف الخبر كـ '{found_negation[0]}' بواسطة {link.split('/')[2]}")
                break
        
        if is_trusted:
            found_trusted = True
            if "؟" not in title: score += 10

    # 3. النتيجة النهائية
    if is_fake:
        verdict = "❌ خبر كاذب / إشاعة"
        score = 15
    elif score > 70 or (found_trusted and score >= 60):
        verdict = "✅ خبر صادق ومؤكد"
        score = min(score, 95)
    else:
        verdict = "⚠️ غير مؤكد / مضلل"
        score = 50
        if not reasons: reasons.append("المعلومات متضاربة أو المصادر الرسمية لم تحسم الخبر بعد")

    return {
        "verdict": verdict,
        "score": score,
        "date_info": f"تم التحقق في: {datetime.datetime.now().strftime('%Y-%m-%d')}",
        "reasons": list(set(reasons))[:2],
        "sources": [{"title": r['title'], "link": r['link']} for r in results[:4]]
    }

# ==========================================
# 🌐 المسارات (Routes)
# ==========================================

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    text = data.get('text', '').strip()
    lang = data.get('lang', 'ar')

    # منع المدخلات القصيرة جداً
    if len(re.findall(r'\w+', text)) < 3:
        return jsonify({"error": "يرجى كتابة جملة كاملة (أكثر من 3 كلمات)"}), 400

    result = deep_analyze_news(text, lang)
    return jsonify(result)

# --- دوار إدارة المستخدمين (مبسطة) ---
def load_db():
    if not os.path.exists(DB_FILE): return {"users": []}
    with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = load_db()
        user = next((u for u in db['users'] if u['username'] == request.form['username']), None)
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return render_template('login.html', error="خطأ في البيانات")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

