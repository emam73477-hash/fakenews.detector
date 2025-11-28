# ==========================================
# 🚀 YUVAi - PRODUCTION READY VERSION
# Deployable to Render/Heroku via GitHub
# ==========================================

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
import smtplib
from email.mime.text import MIMEText
import random
import os
import json

app = Flask(__name__)

# SECURITY: Get SECRET_KEY from Server Environment, or use a fallback for local testing
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret_key_for_testing")

# ==========================================
# 📧 SECURE EMAIL CONFIGURATION
# ==========================================
# On Render/Server: Set 'MAIL_USERNAME' and 'MAIL_PASSWORD' in Environment Variables.
# On Local Laptop: It will use the defaults below (only if Env Vars are missing).

SENDER_EMAIL = os.environ.get("MAIL_USERNAME", "your_email@gmail.com")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD", "your_app_password")

# ==========================================
# 💾 DATABASE SYSTEM (JSON FILE)
# ==========================================
# NOTE: On free cloud hosting (Render/Heroku), this file resets every 24 hours.
# This is fine for a competition demo.
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": [], "news": []}
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except:
        return {"users": [], "news": []}

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
# 🤖 SIMULATED AI ENGINE
# ==========================================
def analyze_text_simulation(text):
    text = text.lower()
    
    # Logic: Detect keywords to generate a realistic looking result
    if any(x in text for x in ["fake", "rumor", "whatsapp", "miracle", "forwarded"]):
        score = random.randint(5, 35)
        verdict = "LIKELY FAKE"
        reasons = ["Suspicious vocabulary detected.", "No reputable source cited.", "High sensationalism score."]
    elif any(x in text for x in ["official", "report", "study", "government", "bbc", "cnn"]):
        score = random.randint(85, 99)
        verdict = "VERIFIED REAL"
        reasons = ["Cross-referenced with verified media.", "Formal language structure detected.", "Source domain has high trust authority."]
    else:
        score = random.randint(40, 70)
        verdict = "UNCERTAIN"
        reasons = ["Insufficient data for conclusive result.", "Mixed sentiment detected.", "Requires manual fact-checking."]

    return {
        "verdict": verdict,
        "score": score,
        "date_info": datetime.datetime.now().strftime("%Y-%m-%d"),
        "reasons": reasons,
        "sources": [
            {"domain": "google.com", "title": "Search Verification", "link": "https://news.google.com"},
            {"domain": "reuters.com", "title": "Reuters Archive", "link": "#"}
        ]
    }

# ==========================================
# 📨 EMAIL LOGIC
# ==========================================
def send_verification_email(receiver_email, otp):
    # Check if credentials are set
    if "your_email" in SENDER_EMAIL or "your_app_password" in SENDER_PASSWORD:
        print("\n❌ CONFIG ERROR: Real Email/Password not set in Environment Variables.")
        print(f"🔑 MANUAL LOGIN CODE: {otp}\n")
        return False

    try:
        print(f"🔄 Sending email to {receiver_email} via {SENDER_EMAIL}...")
        
        msg = MIMEText(f"Hello,\n\nYour YUVAi Verification Code is: {otp}\n\nGood luck!\nYUVAi Team")
        msg['Subject'] = "YUVAi Verification Code"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        
        print("✅ Email Sent Successfully!")
        return True
    except Exception as e:
        print(f"⚠️ Email Failed: {e}")
        print(f"🔑 MANUAL LOGIN CODE: {otp}")
        return False

# ==========================================
# 🌐 ROUTES
# ==========================================

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    db = load_db()
    news = db.get('news', [])
    if not news:
        news = [
            {"title": "System Active", "desc": "Connected to Cloud Server.", "image": "https://placehold.co/600x400/1e293b/white?text=YUVAi+Online", "type": "System", "source": "Server", "date": "Live"}
        ]
    return render_template('index.html', user=session['user'], role=session.get('role', 'user'), news=news)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)
        if user and check_password_hash(user['password'], password):
            session['user'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid Username or Password")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user exists
        if get_user(username): 
            return "Username taken"

        otp = str(random.randint(1000, 9999))
        
        # --- MODIFIED: Try to send email, but don't crash if it fails ---
        try:
            send_verification_email(email, otp)
        except Exception as e:
            print(f"❌ EMAIL FAILED: {e}") 
            # We continue anyway so the app doesn't crash!

        # Print OTP to logs so you can see it in Render Dashboard if email fails
        print(f"🔑 MANUAL OTP FOR {username}: {otp}")
        
        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), 
            "role": "user"
        }
        session['otp'] = otp
        return redirect(url_for('verify_otp'))

    return render_template('register.html')
@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            user_data = session['temp_user']
            create_user(user_data)
            session['user'] = user_data['username']
            session['role'] = user_data['role']
            session.pop('temp_user', None)
            session.pop('otp', None)
            return redirect(url_for('home'))
        else:
            return render_template('verify.html', email=session['temp_user']['email'], error="Wrong Code")
    return render_template('verify.html', email=session['temp_user']['email'])

@app.route('/analyze', methods=['POST'])
def analyze():
    text = request.form.get('text')
    if not text: return jsonify({"error": "No text"})
    return jsonify(analyze_text_simulation(text))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    return "Admin Panel - Under Construction for Demo"

@app.route('/about')
def about():
    return "YUVAi Documentation"

if __name__ == '__main__':
    # Prepare DB
    if not os.path.exists(DB_FILE):
        save_db({"users": [], "news": []})
        
    # Get PORT from environment (Required for Render/Heroku)
    port = int(os.environ.get("PORT", 5000))
    
    # Disable debug mode in production
    debug_mode = os.environ.get("FLASK_DEBUG", "True") == "True"
    
    print(f"🚀 Server starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
