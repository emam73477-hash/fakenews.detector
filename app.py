import os
import json
import datetime
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secure_key_2025")

# ==========================================
# 🔑 الإعدادات (ضع مفتاح SERPER الخاص بك هنا)
# ==========================================
SERPER_API_KEY = "YOUR_SERPER_API_KEY_HERE" 
DB_FILE = "users_db.json"

# قائمة المصادر الموثوقة (إخبارية ورياضية)
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "aljazeera.net", "alarabiya.net", 
    "youm7.com", "skynewsarabia.com", "masrawy.com", "rt.com",
    "cnn.com", "apnews.com", "kooora.com", "yallakora.com", "filgoal.com", "al-ain.com"
]

# قائمة مواقع التحقق من الحقائق
FACT_CHECKERS = [
    "misbar.com", "fatabyyano.net", "dabegad.com", 
    "snopes.com", "politifact.com"
]

# ==========================================
# 🧠 المحرك الذكي: كاشف الإشاعات والعناوين المضللة
# ==========================================
def deep_analyze_news(text, lang="ar"):
    url = "https://google.serper.dev/search"
    
    # 1. كلمات تدل قاطعاً على أن الخبر "تكذيب" أو "إشاعة"
    negation_words = [
        "خدعة", "كذب", "إشاعة", "شائعة", "لا صحة", "نفي", "ينفي", "نفت", 
        "مفبرك", "حقيقة", "توضيح", "يكشف", "رد على", "زيف", "fake", "hoax", "rumor"
    ]

    # 2. تحسين البحث (البحث عن الحقيقة وليس مجرد الكلمات)
    search_query = f"حقيقة {text}" if lang == "ar" else f"truth about {text}"
    
    payload = {
        "q": search_query,
        "gl": "eg" if lang == "ar" else "us",
        "hl": lang,
        "num": 10
    }

    # التحقق من الوقت (أمس، اليوم)
    if any(word in text for word in ["أمس", "اليوم", "yesterday", "today"]):
        payload["tbs"] = "qdr:d2" # فلتر آخر 48 ساعة فقط

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        results = response.json().get("organic", [])

        if not results:
            return {"verdict": "⚠️ غير مؤكد", "score": 50, "reasons": ["لم نجد مصادر كافية حالياً"]}

        # نظام النقاط (يبدأ بـ 50 - محايد)
        score = 50 
        reasons = []
        is_fake = False # مؤشر حاسم للكذب

        for res in results:
            title = res.get("title", "").lower()
            snippet = res.get("snippet", "").lower()
            full_text = title + " " + snippet
            link = res.get("link", "").lower()

            # أ- كشف كلمات "التكذيب" في العنوان أو الوصف (أهم فحص)
            found_negation = [w for w in negation_words if w in full_text]
            
            is_trusted = any(ts in link for ts in TRUSTED_SOURCES)
            is_fact_checker = any(fc in link for fc in FACT_CHECKERS)

            if found_negation:
                # إذا وجدنا كلمة (خدعة/نفي) في مصدر موثوق -> الخبر كاذب فوراً
                if is_trusted or is_fact_checker:
                    is_fake = True
                    reasons.append(f"المصدر {link.split('/')[2]} أكد أنها {found_negation[0]}")
                    break # لا داعي لإكمال البحث، الخبر كاذب
                else:
                    score -= 15 # تقليل الثقة

            elif is_trusted:
                # إذا وجدنا الخبر في مصدر موثوق "بدون" أي كلمات تكذيب أو علامات استفهام
                if "؟" not in title and "?" not in title:
                    score += 15

        # 3. صياغة النتيجة النهائية
        if is_fake or score < 40:
            verdict = "❌ خبر كاذب / إشاعة"
            final_score = 15 # ثقة منخفضة جداً بالخبر
        elif score > 70:
            verdict = "✅ خبر صادق ومؤكد"
            final_score = 90
        else:
            verdict = "⚠️ غير مؤكد / مضلل"
            final_score = 50
            if not reasons: reasons.append("المعلومات متضاربة أو المصادر غير كافية للحسم")

        return {
            "verdict": verdict,
            "score": final_score,
            "date_info": f"تم الفحص بتاريخ: {datetime.datetime.now().strftime('%Y-%m-%d')}",
            "reasons": list(set(reasons))[:2],
            "sources": [{"title": r['title'], "link": r['link']} for r in results[:4]]
        }

    except Exception as e:
        return {"verdict": "خطأ", "score": 0, "reasons": ["فشل الاتصال بالخادم"]}

# ==========================================
# 🌐 مسارات الموقع (Authentication & Routes)
# ==========================================

def load_db():
    if not os.path.exists(DB_FILE): return {"users": []}
    with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

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

    # فحص جودة المدخلات (أكثر من 3 كلمات)
    words = re.findall(r'\w+', text)
    if len(words) < 3:
        return jsonify({"error": "يرجى إدخال 3 كلمات مفهومة على الأقل"}), 400

    result = deep_analyze_news(text, lang)
    return jsonify(result)

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = load_db()
        user = next((u for u in db['users'] if u['username'] == request.form['username']), None)
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return "بيانات خاطئة"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
