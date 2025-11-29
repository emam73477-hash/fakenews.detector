import os
import json
import random
import datetime
import smtplib
import threading
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "competition_secret")

# ==========================================
# 📨 إعدادات الإيميل
# ==========================================
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD")

# قاعدة البيانات المحلية
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
# 🚀 دالة الإرسال المحدثة (FIXED)
# ==========================================
def send_email_logic(receiver_email, otp):
    print(f"\n🔄 [بدء الإرسال] محاولة إرسال كود {otp} إلى: {receiver_email}")
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ [خطأ] متغيرات البيئة (MAIL_USERNAME / MAIL_PASSWORD) غير موجودة!")
        return

    msg = MIMEText(f"مرحباً،\nكود التفعيل الخاص بك هو: {otp}\n\nشكراً لك.")
    msg['Subject'] = "Verification Code"
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email

    try:
        # 🔥 التغيير الرئيسي هنا: استخدام SMTP_SSL ومنفذ 465
        # هذا يحل مشكلة Network unreachable في أغلب الأحيان
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        
        print(f"✅ [نجاح] تم إرسال الإيميل إلى {receiver_email}")
        
    except Exception as e:
        print(f"❌ [فشل الإرسال] السبب: {e}")
        # محاولة بديلة باستخدام المنفذ 587 إذا فشل 465
        try:
            print("🔄 محاولة بديلة عبر المنفذ 587...")
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
            print("✅ [نجاح] تم الإرسال عبر المحاولة البديلة.")
        except Exception as e2:
             print(f"❌ [فشل نهائي] لم ينجح أي منفذ. الخطأ: {e2}")

# ==========================================
# 🌐 صفحة التسجيل
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if get_user(username): 
            return "اسم المستخدم موجود بالفعل"

        otp = str(random.randint(1000, 9999))
        
        # تشغيل الإرسال في الخلفية
        thread = threading.Thread(target=send_email_logic, args=(email, otp))
        thread.start()

        print(f"🔑 [كود احتياطي] للمستخدم {username} هو: {otp}")

        session['temp_user'] = {
            "username": username, 
            "email": email, 
            "password": generate_password_hash(password), 
            "role": "user"
        }
        session['otp'] = otp
        
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

# ==========================================
# باقي الكود (كما هو)
# ==========================================
@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        user_otp = request.form.get('otp', '').strip()
        if user_otp == session.get('otp'):
            create_user(session['temp_user'])
            session['user'] = session['temp_user']['username']
            session['role'] = session['temp_user']['role']
            session.pop('temp_user', None)
            session.pop('otp', None)
            return redirect(url_for('home'))
        return render_template('verify.html', email=session['temp_user']['email'], error="الكود خطأ")
    return render_template('verify.html', email=session['temp_user']['email'])

@app.route('/')
def home():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', user=session['user'], news=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']; session['role'] = user['role']
            return redirect(url_for('home'))
        return render_template('login.html', error="بيانات خاطئة")
    return render_template('login.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    return jsonify({"verdict": "REAL", "score": 95, "date_info": "Today", "reasons": ["AI Analysis"], "sources": []})

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
