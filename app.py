import os
import json
import random
import datetime
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import threading  # <--- NEW IMPORT FOR SPEED

app = Flask(__name__)

# SECURITY
app.secret_key = os.environ.get("SECRET_KEY", "local_secret_key")
SENDER_EMAIL = os.environ.get("MAIL_USERNAME", "your_email@gmail.com")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD", "your_app_password")

# DATABASE
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
# ⚡ FAST EMAIL SENDER (Background)
# ==========================================
def send_async_email(receiver_email, otp):
    """Sends email in the background so the site doesn't freeze"""
    try:
        print(f"🔄 Background: Sending email to {receiver_email}...")
        
        msg = MIMEText(f"Your YUVAi Verification Code is: {otp}")
        msg['Subject'] = "YUVAi Verification"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email

        # USE PORT 465 (SSL) - It is faster and more secure than 587
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        
        print(f"✅ Email Sent to {receiver_email}!")
    except Exception as e:
        print(f"❌ Background Email Failed: {e}")

# ==========================================
# 🚀 REGISTER ROUTE
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if get_user(username): return "Username taken"
        
        otp = str(random.randint(1000, 9999))
        
        # --- THE MAGIC TRICK ---
        # We start a separate "thread" to send the email.
        # The code below runs INSTANTLY without waiting for Gmail.
        email_thread = threading.Thread(target=send_async_email, args=(email, otp))
        email_thread.start()
        
        # Backup: Print to logs just in case
        print(f"🔑 OTP generated for {username}: {otp}")

        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), "role": "user"
        }
        session['otp'] = otp
        
        # User is redirected IMMEDIATELY. No waiting.
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

# --- OTHER ROUTES ---
@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'], role=session.get('role', 'user'), news=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']; session['role'] = user['role']
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            create_user(session['temp_user'])
            session['user'] = session['temp_user']['username']; session['role'] = session['temp_user']['role']
            session.pop('temp_user', None)
            return redirect(url_for('home'))
        return render_template('verify.html', email=session['temp_user']['email'], error="Wrong Code")
    return render_template('verify.html', email=session['temp_user']['email'])

@app.route('/analyze', methods=['POST'])
def analyze():
    text = request.form.get('text', '').lower()
    score = random.randint(80, 99) if "official" in text else random.randint(10, 40)
    return jsonify({"verdict": "REAL" if score > 50 else "FAKE", "score": score, "date_info": "Today", "reasons": ["AI Analysis"], "sources": []})

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
