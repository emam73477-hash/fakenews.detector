import os
import json
import random
import datetime
import smtplib
import threading  # <--- مهم جداً عشان الموقع ميهنجش
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# ==========================================
# 🔐 الإعدادات (مهمة جداً)
# ==========================================
app.secret_key = os.environ.get("SECRET_KEY", "any_secret_key_for_testing")

# هنا بنجيب إيميلك أنت (المرسل) من إعدادات Render
# عشان نقدر نبعت منه رسالة للمستخدم
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD")

# إعداد قاعدة البيانات
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
# 📨 دالة إرسال الإيميل (في الخلفية)
# ==========================================
def send_email_background(receiver_email, otp):
    """
    هذه الدالة تأخذ إيميل المستخدم (receiver_email) 
    وتبعت له الكود باستخدام إيميلك أنت (SENDER_EMAIL)
    """
    try:
        print(f"🔄 جاري الاتصال بسيرفر جوجل للإرسال إلى: {receiver_email}...")
        
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            print("❌ خطأ: لم يتم وضع إيميل المرسل في إعدادات Render")
            return

        # محتوى الرسالة
        subject = "كود التفعيل الخاص بك - YUVAi"
        body = f"مرحباً،\n\nكود التفعيل الخاص بك هو: {otp}\n\nنتمنى لك التوفيق في المسابقة!\n\nفريق YUVAi"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email  # <--- هنا بنحط إيميل الشخص اللي سجل

        # الاتصال بجيميل
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        
        print(f"✅ تم إرسال الإيميل بنجاح إلى {receiver_email}")
        
    except Exception as e:
        print(f"❌ فشل إرسال الإيميل: {e}")

# ==========================================
# 🚀 صفحة التسجيل (Register)
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 1. هنا بنستلم البيانات اللي الشخص كتبها
        username = request.form['username']
        email = request.form['email']    # <--- ده الإيميل اللي الشخص كتبه
        password = request.form['password']
        
        # التأكد إن الاسم مش مستخدم قبل كده
        if get_user(username): 
            return "اسم المستخدم مأخوذ سابقاً. <a href='/register'>حاول مرة أخرى</a>"

        # إنشاء كود عشوائي
        otp = str(random.randint(1000, 9999))
        
        # 2. إرسال الإيميل في الخلفية (Threading)
        # بنبعت المتغير 'email' اللي الشخص كتبه للدالة
        try:
            thread = threading.Thread(target=send_email_background, args=(email, otp))
            thread.start()
        except Exception as e:
            print(f"خطأ في الـ Thread: {e}")

        # طباعة الكود في الـ Logs كاحتياطي
        print(f"🔑 كود الطوارئ للمستخدم {username}: {otp}")

        # حفظ بيانات مؤقتة
        session['temp_user'] = {
            "username": username, "email": email, 
            "password": generate_password_hash(password), 
            "role": "user"
        }
        session['otp'] = otp
        
        # النقل لصفحة التفعيل فوراً
        return redirect(url_for('verify_otp'))

    return render_template('register.html')

# ==========================================
# باقي الصفحات (Verify, Login, Home)
# ==========================================

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
        return render_template('verify.html', email=session['temp_user']['email'], error="الكود غير صحيح")
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
        return render_template('login.html', error="بيانات خاطئة")
    return render_template('login.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    # محاكاة للذكاء الاصطناعي عشان العرض
    text = request.form.get('text', '').lower()
    score = random.randint(80, 99) if "official" in text else random.randint(10, 40)
    verdict = "REAL" if score > 50 else "FAKE"
    return jsonify({"verdict": verdict, "score": score, "date_info": "Today", "reasons": ["AI Analysis"], "sources": []})

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
