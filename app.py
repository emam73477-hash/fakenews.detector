import os
import json
import datetime
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pro_secret_key_123")

# ==========================================
# 🔑 الإعدادات والمفاتيح
# ==========================================
SERPER_API_KEY = "YOUR_SERPER_KEY_HERE" # ضع مفتاحك هنا
DB_FILE = "database.json"

TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "aljazeera.net", "alarabiya.net", 
    "youm7.com", "skynewsarabia.com", "masrawy.com", "rt.com",
    "cnn.com", "apnews.com", "kooora.com", "yallakora.com", "filgoal.com"
]

FACT_CHECKERS = [
    "misbar.com", "fatabyyano.net", "dabegad.com", 
    "snopes.com", "politifact.com", "fullfact.org"
]

# ==========================================
# 📂 إدارة قاعدة البيانات المصغرة
# ==========================================
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": []}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==========================================
# 🧠 محرك التحليل الذكي (القلب النابض)
# ==========================================
def deep_analyze_news(text, lang="ar"):
    url = "https://google.serper.dev/search"
    today = datetime.datetime.now()
    
    # 1. تحليل الكلمات الزمنية وتحديد فلتر الوقت (Freshness)
    # qdr:d (آخر يوم), qdr:d2 (آخر يومين), qdr:w (أسبوع)
    time_filters = {
        "ar": {"أمس": "qdr:d2", "امس": "qdr:d2", "اليوم": "qdr:d", "عاجل": "qdr:h", "الآن": "qdr:h"},
        "en": {"yesterday": "qdr:d2", "today": "qdr:d", "urgent": "qdr:h", "now": "qdr:h"}
    }
    
    tbs_value = ""
    for word, filter_val in time_filters[lang].items():
        if word in text:
            tbs_value = filter_val
            break

    # 2. الكلمات المناقضة (لكشف التضارب: فوز ضد خسارة)
    opposites = {
        "خسارة": ["فوز", "انتصار", "تغلب", "فاز", "توج"],
        "loss": ["win", "victory", "won", "scored"],
        "وفاة": ["ينفي", "إشاعة", "بصحة جيدة", "بخير", "توضيح"],
        "death": ["alive", "denies", "healthy", "safe"]
    }

    # 3. كلمات النفي (لكشف العناوين المضللة)
    negation_signals = ["شائعة", "لا صحة", "نفت", "خبر كاذب", "غير صحيح", "ينفي", "مفبرك", "إشاعة", "false", "fake", "rumor"]

    # إعداد البحث
    query = f"{text} حقيقة" if lang == "ar" else f"{text} truth"
    payload = {
        "q": query,
        "gl": "eg" if lang == "ar" else "us",
        "hl": lang,
        "num": 8
    }
    if tbs_value: payload["tbs"] = tbs_value

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        results = response.json().get("organic", [])

        if not results:
            return {"verdict": "⚠️ غير مؤكد", "score": 50, "reasons": ["لم نجد مصادر رسمية كافية حالياً"]}

        points = 50 
        reasons = []
        contradiction_found = False

        for res in results:
            title = res.get("title", "").lower()
            snippet = res.get("snippet", "").lower()
            content = title + " " + snippet
            link = res.get("link", "").lower()

            # أ- فحص التناقض (لو المستخدم قال خسارة وجوجل قال فوز)
            for key, words in opposites.items():
                if key in text:
                    if any(w in content for w in words):
                        points -= 40
                        contradiction_found = True
                        reasons.append(f"تضارب: المصادر تتحدث عن ({words[0]}) وليس ({key})")
                        break

            # ب- فحص النفي (العناوين المضللة)
            if any(sig in content for sig in negation_signals):
                points -= 30
                reasons.append(f"تم رصد كلمات تكذيب في {link.split('/')[2]}")

            # ج- فحص المصادر الموثوقة
            if any(ts in link for ts in TRUSTED_SOURCES):
                if not contradiction_found: points += 15
            
            if any(fc in link for fc in FACT_CHECKERS):
                if any(sig in content for sig in negation_signals):
                    points = 10 # تكذيب قاطع من مدقق حقائق
                    reasons.append("مدقق حقائق رسمي أكد أنها إشاعة")

        # النتيجة النهائية
        if points <= 35:
            verdict = "❌ خبر كاذب / إشاعة"
        elif points >= 75:
            verdict = "✅ خبر صادق ومؤكد"
        else:
            verdict = "⚠️ مشكوك فيه / مضلل"

        return {
            "verdict": verdict,
            "score": max(0, min(100, points)),
            "reasons": list(set(reasons))[:2],
            "date_info": f"تاريخ التحقق: {today.strftime('%Y-%m-%d')}",
            "sources": [{"title": r['title'], "link": r['link']} for r in results[:3]]
        }

    except Exception as e:
        return {"verdict": "خطأ", "score": 0, "reasons": ["فشل الاتصال بالخادم"]}

# ==========================================
# 🌐 مسارات الموقع (Routes)
# ==========================================

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"error": "غير مصرح لك"}), 401
    
    data = request.get_json()
    text = data.get('text', '').strip()
    lang = data.get('lang', 'ar')

    # 1. التحقق من الطول (3 كلمات على الأقل)
    words = re.findall(r'\w+', text)
    if len(words) < 3:
        return jsonify({"error": "يرجى إدخال 3 كلمات مفهومة على الأقل لضمان الدقة"}), 400

    # 2. التحقق من وجود حروف
    if not any(c.isalpha() for c in text):
        return jsonify({"error": "النص يحتوي على رموز فقط، يرجى كتابة خبر حقيقي"}), 400

    result = deep_analyze_news(text, lang)
    return jsonify(result)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = load_db()
        username = request.form['username']
        password = request.form['password']
        user = next((u for u in db['users'] if u['username'] == username), None)
        if user and check_password_hash(user['password'], password):
            session['user'] = username
            return redirect(url_for('home'))
        return render_template('login.html', error="بيانات الدخول خاطئة")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = load_db()
        username = request.form['username']
        if any(u['username'] == username for u in db['users']):
            return "اسم المستخدم موجود مسبقاً"
        
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
    app.run(debug=True, port=5000)
