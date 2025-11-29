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
# 1. Email Config (Brevo)
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") 
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")

# 2. Search Config (Serper.dev)
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")

# List of Global Trusted Sources
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com"
]

# List of Fact Checking Sites
FACT_CHECKERS = [
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org"
]

# ==========================================
# 🗄️ Database & Helpers
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE): return {"users": [], "news": []}
    try: with open(DB_FILE, 'r') as f: return json.load(f)
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
# 📧 Email Logic (HTTP API - Safe for Render)
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
        "subject": "Your Verification Code",
        "htmlContent": f"""
        <div style='font-family: Arial; padding: 20px;'>
            <h2>Welcome!</h2>
            <p>Your activation code is:</p>
            <h1 style='color: #2563eb;'>{otp}</h1>
        </div>
        """
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"✅ Email sent to {receiver_email}")
    except Exception as e: 
        print(f"❌ Email Error: {e}")

# ==========================================
# 🧠 AI Core: News Analysis Logic
# ==========================================
def analyze_news_logic(text):
    """
    Searches Google for the text and analyzes credibility.
    """
    url = "https://google.serper.dev/search"
    # q=query, gl=country(us), hl=language(en)
    payload = json.dumps({"q": text, "gl": "us", "hl": "en"}) 
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        
        organic_results = data.get("organic", [])
        
        verdict = "UNVERIFIED"
        score = 50 # Base score
        found_sources = []
        reasons = []
        date_info = "Date unavailable"

        # No results found?
        if not organic_results:
            return {
                "verdict": "FAKE",
                "score": 0,
                "date_info": "N/A",
                "reasons": ["No search results found for this headline."],
                "sources": []
            }

        # Analyze Results
        for result in organic_results:
            link = result.get("link", "")
            title = result.get("title", "")
            date = result.get("date", "")
            
            # 1. Capture the date of the first result
            if date and date_info == "Date unavailable":
                date_info = f"First seen: {date}"

            # 2. Check Trusted Sources (+ Score)
            for trusted in TRUSTED_SOURCES:
                if trusted in link:
                    score += 20
                    reasons.append(f"Confirmed by trusted source: {trusted}")
                    found_sources.append({"title": title, "link": link, "type": "Trusted ✅"})

            # 3. Check Fact Checkers (- Score)
            for checker in FACT_CHECKERS:
                if checker in link:
                    # If a fact checker wrote about it, it's usually to debunk it,
                    # but we check the title for keywords like 'False' or 'Hoax'.
                    score -= 10 
                    found_sources.append({"title": title, "link": link, "type": "Fact Check ⚖️"})
                    if any(x in title.lower() for x in ["false", "fake", "hoax", "scam", "myth"]):
                        score = 10
                        verdict = "FAKE"
                        reasons.append(f"Debunked by {checker}")

        # Final Decision
        if score >= 80:
            verdict = "REAL"
        elif score <= 30:
            verdict = "FAKE"
        else:
            verdict = "UNSURE"

        return {
            "verdict": verdict,
            "score": min(score, 100),
            "date_info": date_info,
            "reasons": list(set(reasons)), # Remove duplicates
            "sources": found_sources[:5]   # Top 5 sources
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
    
    if not news_text:
        return jsonify({"error": "Please enter text"}), 400
        
    result = analyze_news_logic(news_text)
    return jsonify(result)

# --- Auth Routes (Same as before, just English) ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if get_user(username): return "Username already exists"
        
        otp = str(random.randint(1000, 9999))
        
        # Send email in background
        thread = threading.Thread(target=send_email_logic, args=(email, otp))
        thread.start()

        # Log OTP for backup
        print(f"🔑 [BACKUP OTP] For {email}: {otp}")

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
        return render_template('login.html', error="Invalid Username or Password")
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
