import os
import json
import random
import datetime
import threading
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "competition_secret")

# ==========================================
# 🔑 API KEYS (Set these in Render Env Vars)
# ==========================================
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") 
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")

# ==========================================
# 🌍 Updated Trusted Sources (English + Arabic)
# ==========================================
TRUSTED_SOURCES = [
    # English Global
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com",
    # Arabic / Regional
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com", 
    "masrawy.com", "shorouknews.com", "independentarabia.com", "bbc.com/arabic"
]

# Updated Fact Checkers
FACT_CHECKERS = [
    # English
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org",
    # Arabic
    "fatabyyano.net", "misbar.com", "dabegad.com"
]

# ==========================================
# 🗄️ Database & Helpers
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
    for user in db['users']:
        if user['username'] == user_data['username']: return False
    user_data['created_at'] = str(datetime.datetime.now())
    db['users'].append(user_data)
    save_db(db)
    return True

# ==========================================
# 📧 Email Logic
# ==========================================
def send_email_logic(receiver_email, otp):
    if not SENDER_EMAIL or not BREVO_API_KEY:
        print("❌ Error: Brevo credentials missing.")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json", 
        "api-key": BREVO_API_KEY, 
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "FakeNews Detector", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "Verification Code / كود التفعيل",
        "htmlContent": f"""
        <div style='font-family: Arial; padding: 20px; text-align: center;'>
            <h2>Welcome! / مرحباً</h2>
            <p>Your activation code is:</p>
            <h1 style='color: #2563eb; font-size: 30px;'>{otp}</h1>
        </div>
        """
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"✅ Email sent to {receiver_email}")
    except Exception as e: 
        print(f"❌ Email Error: {e}")

# ==========================================
# 🧠 AI Core: Multi-Language News Analysis
# ==========================================
def analyze_news_logic(text, lang="en"):
    """
    Searches Google and returns results in the requested language (en or ar).
    """
    url = "https://google.serper.dev/search"
    
    # 🌍 1. Configure Search Region & Language
    if lang == 'ar':
        # Search in Egypt (eg) with Arabic language (ar)
        payload = json.dumps({"q": text, "gl": "eg", "hl": "ar"})
        
        # Arabic UI Labels
        LBL_REAL = "خبر حقيقي"
        LBL_FAKE = "خبر زائف"
        LBL_UNSURE = "غير مؤكد"
        LBL_DATE = "أول ظهور للخبر: "
        LBL_NO_RES = "لم يتم العثور على نتائج."
        LBL_TRUSTED = "تم التأكيد عبر مصدر موثوق: "
        LBL_FACT = "تم تصنيفه بواسطة مدقق حقائق: "
        FAKE_KEYWORDS = ["كاذب", "زائف", "شائعة", "غير صحيح", "خاطئ", "مفبرك"]
    else:
        # Search in US (us) with English language (en)
        payload = json.dumps({"q": text, "gl": "us", "hl": "en"})
        
        # English UI Labels
        LBL_REAL = "REAL"
        LBL_FAKE = "FAKE"
        LBL_UNSURE = "UNVERIFIED"
        LBL_DATE = "First seen: "
        LBL_NO_RES = "No search results found."
        LBL_TRUSTED = "Confirmed by trusted source: "
        LBL_FACT = "Flagged by fact checker: "
        FAKE_KEYWORDS = ["false", "fake", "hoax", "scam", "myth", "debunked"]

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        
        organic_results = data.get("organic", [])
        
        verdict = LBL_UNSURE
        score = 50 
        found_sources = []
        reasons = []
        date_info = "Date unavailable" if lang == 'en' else "التاريخ غير متوفر"

        if not organic_results:
            return {
                "verdict": LBL_FAKE,
                "score": 0,
                "date_info": "N/A",
                "reasons": [LBL_NO_RES],
                "sources": []
            }

        # 🧠 2. Analyze Results
        for result in organic_results:
            link = result.get("link", "")
            title = result.get("title", "")
            date = result.get("date", "")
            
            # Capture date
            if date and (date_info.startswith("Date") or date_info.startswith("التاريخ")):
                date_info = f"{LBL_DATE}{date}"

            # Check Trusted Sources
            for trusted in TRUSTED_SOURCES:
                if trusted in link:
                    score += 20
                    reasons.append(f"{LBL_TRUSTED}{trusted}")
                    found_sources.append({"title": title, "link": link, "type": "Trusted"})

            # Check Fact Checkers
            for checker in FACT_CHECKERS:
                if checker in link:
                    score -= 20
                    found_sources.append({"title": title, "link": link, "type": "Fact Check"})
                    
                    # Check title for negative keywords
                    if any(k in title.lower() for k in FAKE_KEYWORDS):
                        score = 10
                        verdict = LBL_FAKE
                        reasons.append(f"{LBL_FACT}{checker}")

        # ⚖️ 3. Final Verdict
        if score >= 80:
            verdict = LBL_REAL
        elif score <= 30:
            verdict = LBL_FAKE
        else:
            verdict = LBL_UNSURE

        return {
            "verdict": verdict,
            "score": min(score, 100),
            "date_info": date_info,
            "reasons": list(set(reasons)),
            "sources": found_sources[:5]
        }

    except Exception as e:
        print(f"Analysis Error: {e}")
        return {"verdict": "ERROR", "score": 0, "reasons": ["Connection error"], "sources": []}

# ==========================================
# 🌐 Routes
# ==========================================
@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: 
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    news_text = data.get('text', '')
    # 🔥 Get Language from Frontend (default to English)
    lang = data.get('lang', 'en') 
    
    if not news_text:
        return jsonify({"error": "Empty text"}), 400
        
    # Pass language to logic function
    result = analyze_news_logic(news_text, lang)
    return jsonify(result)

# --- Auth Routes ---

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

        print(f"🔑 [BACKUP OTP] {email}: {otp}")

        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), "role": "user"
        }
        session['otp'] = otp
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        user_code = request.form.get('otp', '').strip()
        if user_code == session.get('otp'):
            create_user(session['temp_user'])
            session['user'] = session['temp_user']['username']
            session.pop('temp_user', None)
            return redirect(url_for('home'))
        return render_template('verify.html', email=session['temp_user']['email'], error="Invalid Code")
    return render_template('verify.html', email=session['temp_user']['email'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid Login")
    return render_template('login.html')

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'], news=[])

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
