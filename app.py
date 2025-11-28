import os
import json
import random
import datetime
import smtplib
import threading  # <--- The Secret to making it work on Render
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# ==========================================
# 🔐 CONFIGURATION
# ==========================================
app.secret_key = os.environ.get("SECRET_KEY", "local_secret")

# GET EMAIL KEYS FROM RENDER SETTINGS
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD")

# DATABASE SETUP
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
# 📨 THE REAL EMAIL SENDER (Background Worker)
# ==========================================
def send_email_background(receiver_email, otp):
    """
    This runs in the background. 
    It connects to Gmail and sends the REAL email.
    """
    try:
        print(f"🔄 Connecting to Gmail to send to {receiver_email}...")
        
        # Check if password is set
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            print("❌ ERROR: Email/Password not set in Render Environment Variables!")
            return

        msg = MIMEText(f"Hello,\n\nYour Verification Code is: {otp}\n\nGood luck with the competition!\n\n- YUVAi Team")
        msg['Subject'] = "YUVAi Verification Code"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email

        # Connect to Gmail Server (Standard Port 587)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Secure the connection
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        
        print(f"✅ EMAIL SENT SUCCESSFULLY to {receiver_email}!")
        
    except Exception as e:
        print(f"❌ EMAIL FAILED: {e}")
        print("Check that your App Password is correct and Environment Variables are set.")

# ==========================================
# 🚀 ROUTES
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if get_user(username): 
            return "Username taken. <a href='/register'>Try again</a>"

        otp = str(random.randint(1000, 9999))
        
        # --- SEND EMAIL IN BACKGROUND ---
        # This prevents the "CRITICAL WORKER TIMEOUT" error
        # The user goes to the next page INSTANTLY, while the email sends in the background.
        try:
            thread = threading.Thread(target=send_email_background, args=(email, otp))
            thread.start()
        except Exception as e:
            print(f"Thread Error: {e}")

        # Always print to logs as backup
        print(f"🔑 BACKUP OTP FOR {username}: {otp}")

        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), 
            "role": "user"
        }
        session['otp'] = otp
        
        # Go to verify page immediately
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            create_user(session['temp_user'])
            session['user'] = session['temp_user']['username']
            session['role'] = session['temp_user']['role']
            session.pop('temp_user', None)
            return redirect(url_for('home'))
        return render_template('verify.html', email=session['temp_user']['email'], error="Wrong Code")
    return render_template('verify.html', email=session['temp_user']['email'])

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
