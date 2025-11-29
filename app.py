import os
import json
import random
import datetime
import threading
import requests  # 👈 مكتبة جديدة للاتصال بدلاً من smtplib
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "competition_secret")

# ==========================================
# 📨 إعدادات Brevo API (بديل Gmail SMTP)
# ==========================================
# 1. MAIL_USERNAME: إيميلك المسجل في Brevo
# 2. MAIL_PASSWORD: ضع هنا API Key (يبدأ بـ xkeysib-)
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
API_KEY = os.environ.get("MAIL_PASSWORD")

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
# 🚀 دالة الإرسال الجديدة (HTTP API)
# ==========================================
def send_email_logic(receiver_email, otp):
    print(f"\n🔄 [بدء الإرسال] محاولة إرسال كود {otp} إلى: {receiver_email}")
    
    if not SENDER_EMAIL or not API_KEY:
        print("❌ [خطأ] البيانات ناقصة! تأكد من إعداد MAIL_USERNAME و MAIL_PASSWORD في Render")
        return

    # رابط API الخاص بـ Brevo
    url = "https://api.brevo.com/v3/smtp/email"
    
    # إعدادات الرأس (Headers)
    headers = {
        "accept": "application/json",
        "api-key": API_KEY,
        "content-type": "application/json"
    }
    
    # محتوى الرسالة
    payload = {
        "sender": {"name": "Fake News Detector", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "Verification Code",
        "htmlContent": f"""
        <html>
            <body>
                <h2>مرحباً بك!</h2>
                <p>كود التفعيل الخاص بك هو:</p>
                <h1 style="color: blue;">{otp}</h1>
                <p>شكراً لاستخدامك تطبيقنا.</p>
            </body>
        </html>
        """
    }

    try:
        # الإرسال باستخدام requests (لن يتم حظره أبداً)
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ [نجاح] تم إرسال الإيميل! ID: {response.json().get('messageId')}")
        else:
            print(f"❌ [فشل] رد السيرفر: {response.text}")
            
    except Exception as e:
        print(f"❌ [خطأ في الاتصال] السبب: {e}")

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
        
        # تشغيل الإرسال في الخلفية (Thread)
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
# باقي الكود كما هو تماماً
# ==========================================
@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_user' not in session: return redirect(url_for('register'))
    if request.method == 'POST':
        # استخدام strip() لإزالة المسافات الزائدة
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
