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
# 🔑 API KEYS (تأكد من وضع مفاتيحك هنا)
# ==========================================
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") 
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")

# ==========================================
# 🌍 Trusted Sources & Fact Checkers
# ==========================================
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int",
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com", 
    "masrawy.com", "shorouknews.com", "independentarabia.com"
]

FACT_CHECKERS = [
    "fatabyyano.net", "misbar.com", "dabegad.com", 
    "snopes.com", "politifact.com", "factcheck.org"
]

# ==========================================
# 🧠 AI Core: تحليل ذكي يكتشف العناوين المضللة
# ==========================================
def analyze_news_logic(text, lang="ar"):
    url = "https://google.serper.dev/search"
    
    # كلمات النفي التي تظهر في وصف الخبر حتى لو كان العنوان مضلل
    debunk_signals = {
        "ar": ["شائعة", "لا صحة", "نفت", "خبر كاذب", "غير صحيح", "ينفي", "توضيح", "حقيقة", "مفبرك"],
        "en": ["rumor", "false", "denied", "fake news", "not true", "debunked", "clarification", "fact check"]
    }

    # تحسين البحث بإضافة كلمة "حقيقة" لضمان ظهور نتائج التحقق
    search_query = f"{text} حقيقة" if lang == "ar" else f"{text} truth"
    
    payload = json.dumps({
        "q": search_query, 
        "gl": "eg" if lang=="ar" else "us", 
        "hl": lang,
        "num": 8 # زيادة عدد النتائج لدقة أعلى
    })
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        results = response.json().get("organic", [])

        if not results:
            return {"verdict": "⚠️ غير مؤكد", "score": 50, "reasons": ["لم نجد مصادر كافية"]}

        fake_points = 0
        real_points = 0
        reasons = []
        found_sources = []
        
        # تحليل كل نتيجة بحث بعمق
        for res in results:
            title = res.get("title", "").lower()
            snippet = res.get("snippet", "").lower()
            link = res.get("link", "").lower()
            full_content = title + " " + snippet

            # 1. صيد "كلمات النفي" داخل العنوان أو الوصف
            found_negation = [word for word in debunk_signals[lang] if word in full_content]
            
            # 2. فحص المصدر
            is_fact_checker = any(fc in link for fc in FACT_CHECKERS)
            is_trusted = any(ts in link for ts in TRUSTED_SOURCES)

            if found_negation:
                if is_fact_checker or is_trusted:
                    fake_points += 45 # ثقل كبير للتكذيب من مصدر موثوق
                    reasons.append(f"تأكيد من {link.split('/')[2]} أن الخبر إشاعة")
                else:
                    fake_points += 25 # ثقل متوسط لتكذيب من مصدر عام
            
            elif is_trusted:
                # إذا وجدنا الخبر في مصدر موثوق وبدون أي كلمات نفي
                real_points += 30

            found_sources.append({"title": res['title'], "link": res['link']})

        # --- القرار النهائي ---
        if fake_points > real_points:
            verdict = "❌ خبر كاذب (إشاعة)"
            score = 20
        elif real_points > 50:
            verdict = "✅ خبر صادق ومؤكد"
            score = 90
        else:
            verdict = "⚠️ خبر مشكوك فيه أو مضلل"
            score = 45
            reasons.append("المعلومات متضاربة؛ العنوان قد يكون مضللاً بينما المحتوى ينفي.")

        # استخراج أول ظهور (أقدم تاريخ)
        dates = [res.get("date") for res in results if res.get("date")]
        date_info = f"أول ظهور تم رصده: {dates[-1]}" if dates else "التاريخ غير محدد بدقة"

        return {
            "verdict": verdict,
            "score": score,
            "date_info": date_info,
            "reasons": list(set(reasons))[:2],
            "sources": found_sources[:4]
        }

    except Exception as e:
        return {"verdict": "خطأ في الاتصال", "score": 0, "reasons": [str(e)]}

# ==========================================
# 🌐 Routes & Web Logic
# ==========================================
@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    text = data.get('text', '').strip()
    lang = data.get('lang', 'ar')

    # شرط 3 كلمات مفهومة (تجاوز الرموز)
    words = re.findall(r'\w+', text)
    if len(words) < 3:
        msg = "يرجى إدخال 3 كلمات مفهومة على الأقل" if lang == 'ar' else "Min 3 words required"
        return jsonify({"error": msg}), 400

    if not any(c.isalpha() for c in text):
        msg = "يجب إدخال كلمات وليس رموزاً فقط" if lang == 'ar' else "Use actual words"
        return jsonify({"error": msg}), 400

    result = analyze_news_logic(text, lang)
    return jsonify(result)

# --- نظام تسجيل الدخول (بإيجاز) ---

DB_FILE = "local_db.json"
def load_db():
    if not os.path.exists(DB_FILE): return {"users": []}
    with open(DB_FILE, 'r') as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = load_db()
        username = request.form['username']
        hashed_pw = generate_password_hash(request.form['password'])
        db['users'].append({"username": username, "password": hashed_pw})
        save_db(db)
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)


