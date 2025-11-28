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
# 📨 إعدادات الإيميل (من Render)
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
# 🚀 دالة الإرسال (تعمل في الخلفية)
# ==========================================
def send_email_logic(receiver_email, otp):
    """
    هذه الدالة هي المسؤولة عن إرسال الإيميل فعلياً
    """
    print(f"\n🔄 [بدء الإرسال] محاولة إرسال كود {otp} إلى الإيميل: {receiver_email}")
    
    # 1. التأكد من وجود إيميل المرسل
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ [خطأ] لم يتم ضبط إيميل المرسل في إعدادات Render!")
        return

    try:
        # إعداد الرسالة
        msg = MIMEText(f"مرحباً،\nكود التفعيل الخاص بك في YUVAi هو: {otp}\n\nبالتوفيق!")
        msg['Subject'] = "كود تفعيل الحساب"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email

        # 2. الاتصال بسيرفر جوجل
        # نستخدم المنفذ 587 لأنه الأكثر استقراراً مع Render
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # تشفير الاتصال
        
        # 3. تسجيل الدخول
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # 4. الإرسال
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        
        print(f"✅ [تم بنجاح] وصلت الرسالة إلى {receiver_email}")
        
    except Exception as e:
        print(f"❌ [فشل الإرسال] السبب: {e}")
        print("تأكد أنك تستخدم App Password وليس كلمة السر العادية")

# ==========================================
# 🌐 صفحة التسجيل
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # التأكد من عدم تكرار الاسم
        if get_user(username): return "اسم المستخدم موجود بالفعل"

        # إنشاء الكود
        otp = str(random.randint(1000, 9999))
        
        # تشغيل الإرسال في الخلفية (Thread) عشان الموقع ميعلقش
        # بنبعت الإيميل اللي الشخص كتبه (email) للدالة
        thread = threading.Thread(target=send_email_logic, args=(email, otp))
        thread.start()

        # طباعة الكود في السجلات احتياطياً
        print(f"🔑 [كود احتياطي] للمستخدم {username} هو: {otp}")

        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), 
            "role": "user"
        }
        session['otp'] = otp
        
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

# باقي الصفحات (زي ما هي)
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

