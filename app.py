import os
import json
import datetime
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "final_version_key_2025")

# ==========================================
# 🔑 الإعدادات (تأكد من وضع المفتاح الصحيح)
# ==========================================
SERPER_API_KEY = "YOUR_SERPER_API_KEY_HERE" 
DB_FILE = "database.json"

# تم توسيع المصادر لتشمل المواقع التي تنشر التحقيقات الفنية والرياضية
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "aljazeera.net", "alarabiya.net", 
    "youm7.com", "skynewsarabia.com", "masrawy.com", "rt.com",
    "cnn.com", "apnews.com", "kooora.com", "yallakora.com", "filgoal.com",
    "al-ain.com", "elwatannews.com", "elnabaa.net"
]

FACT_CHECKERS = [
    "misbar.com", "fatabyyano.net", "dabegad.com", 
    "snopes.com", "politifact.com", "fullfact.org"
]

# ==========================================
# 🧠 المحرك الذكي (إصدار 3.0 المطور)
# ==========================================
def deep_analyze_news(text, lang="ar"):
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    # 1. إستراتيجية البحث المرنة (Fallback Strategy)
    # إذا لم يجد نتائج بكلمة "حقيقة"، يبحث بالنص الأصلي لضمان عدم ظهور "غير مؤكد"
    search_queries = [f"حقيقة {text}", text] if lang == "ar" else [f"truth about {text}", text]
    
    results = []
    active_query = ""
    for q in search_queries:
        payload = {
            "q": q,
            "gl": "eg" if lang == "ar" else "us",
            "hl": lang,
            "num": 10
        }
        
        # إضافة فلتر الوقت التلقائي (أمس/اليوم)
        if any(word in text for word in ["أمس", "امس", "اليوم", "yesterday", "today"]):
            payload["tbs"] = "qdr:d2"

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                results = response.json().get("organic", [])
                if results:
                    active_query = q
                    break
        except: continue

    if not results:
        return {"verdict": "⚠️ غير مؤكد", "score": 50, "reasons": ["لم نجد نتائج بحث كافية حالياً، تأكد من صحة الكلمات."]}

    # 2. تحليل المحتوى (كشف التناقض والعناوين المضللة)
    points = 50
    reasons = []
    
    # كلمات النفي (لو ظهرت في العنوان الموثوق تعني أن الخبر كاذب)
    negation_words = ["خدعة", "كذب", "إشاعة", "شائعة", "لا صحة", "نفت", "ينفي", "مفبرك", "زيف", "حقيقة"]
    
    # كلمات التناقض (فوز ضد خسارة)
    opposites = {
        "خسارة": ["فوز", "انتصار", "تغلب", "فاز"],
        "وفاة": ["بخير", "بصحة", "ينفي", "إشاعة", "تكذب"],
        "loss": ["win", "victory", "won"],
        "death": ["alive", "healthy", "denies"]
    }

    is_debunked = False
    confirmed_by_official = False

    for res in results:
        title = res.get("title", "").lower()
        snippet = res.get("snippet", "").lower()
        content = title + " " + snippet
        link = res.get("link", "").lower()

        # أ- فحص "العنوان المضلل" (مثل: خدعة وفاة...)
        # إذا وجدنا كلمة نفي في موقع موثوق -> الخبر كاذب فوراً
        is_trusted = any(ts in link for ts in TRUSTED_SOURCES)
        is_checker = any(fc in link for fc in FACT_CHECKERS)
        
        found_negations = [w for w in negation_words if w in content]
        
        if found_negations:
            if is_trusted or is_checker:
                is_debunked = True
                reasons.append(f"تم كشف الخبر كـ '{found_negations[0]}' بواسطة {link.split('/')[2]}")
                break # لا داعي للفحص أكثر، الخبر كاذب
        
        # ب- فحص التناقض (خسارة ضد فوز)
        for key, words in opposites.items():
            if key in text:
                if any(w in content for w in words):
                    is_debunked = True
                    reasons.append(f"تضارب: المصادر الرسمية تتحدث عن ({words[0]})")
                    break

        # ج- فحص التأكيد (لو الخبر موجود في وكالة أنباء بدون كلمات شك)
        if is_trusted and not any(w in content for w in negation_words):
            if "؟" not in title: # العناوين الاستفهامية غالباً مضللة
                confirmed_by_official = True
                points += 15

    # 3. صياغة القرار النهائي
    if is_debunked:
        verdict = "❌ خبر كاذب / إشاعة"
        score = 15
    elif confirmed_by_official and points >= 65:
        verdict = "✅ خبر صادق ومؤكد"
        score = min(points, 95)
    else:
        verdict = "⚠️ غير مؤكد / مضلل"
        score = 50
        if not reasons: reasons.append("المعلومات متضاربة أو المصادر الرسمية لم تنشر تفاصيل حاسمة.")

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

    # فحص الجودة
    words = re.findall(r'\w+', text)
    if len(words) < 3:
        return jsonify({"error": "يرجى كتابة خبر كامل (3 كلمات على الأقل)"}), 400

    result = deep_analyze_news(text, lang)
    return jsonify(result)

# --- نظام تسجيل الدخول ---
def load_db():
    if not os.path.exists(DB_FILE): return {"users": []}
    with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = load_db()
        user = next((u for u in db['users'] if u['username'] == request.form['username']), None)
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return render_template('login.html', error="خطأ في اسم المستخدم أو كلمة المرور")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = load_db()
        username = request.form['username']
        if any(u['username'] == username for u in db['users']): return "المستخدم موجود"
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
if __name__ == '__main__':
    app.run(debug=True)


