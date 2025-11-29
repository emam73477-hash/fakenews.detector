import os
import random
import requests # مكتبة للاتصال عبر HTTP
from flask import Flask, render_template_string, request, redirect, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_123")

# ================================
#  إعدادات Brevo (Sendinblue)
# ================================
# تأكد من وضع هذه القيم في Render Environment Variables
SENDER_EMAIL = os.environ.get("MAIL_USERNAME") # إيميلك المسجل في Brevo
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD") # مفتاح API يبدأ بـ xkeysib-

# ================================
#  دالة إرسال الإيميل (Brevo API)
# ================================
def send_email_logic(receiver_email, otp):
    print(f"\n🔄 [بدء الإرسال] إلى: {receiver_email}")

    if not SENDER_EMAIL or not BREVO_API_KEY:
        print("❌ [خطأ] البيانات ناقصة! تأكد من MAIL_USERNAME و MAIL_PASSWORD")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": "تطبيق التحقق", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "كود التحقق الخاص بك",
        "htmlContent": f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2 style="color: #2563eb;">مرحباً بك!</h2>
            <p>كود التفعيل الخاص بك هو:</p>
            <h1 style="background: #f3f4f6; padding: 10px; display: inline-block; letter-spacing: 5px;">{otp}</h1>
            <p>صلاحية الكود 10 دقائق.</p>
        </div>
        """
    }

    try:
        # الإرسال عبر HTTP (لن يتم حظره بواسطة Render)
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ تم الإرسال بنجاح! Message ID: {response.json().get('messageId')}")
            return True
        else:
            print(f"❌ فشل الإرسال من Brevo: {response.text}")
            return False

    except Exception as e:
        print(f"❌ حدث خطأ في الاتصال: {e}")
        return False

# ================================
#  Templates (HTML مدمج للتسهيل)
# ================================
REGISTER_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تسجيل جديد</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-lg shadow-md w-96">
        <h2 class="text-2xl font-bold mb-6 text-center text-blue-600">إنشاء حساب</h2>
        <form method="POST">
            <input type="email" name="email" required placeholder="أدخل بريدك الإلكتروني" 
                   class="w-full p-3 mb-4 border rounded focus:outline-blue-500">
            <button type="submit" class="w-full bg-blue-600 text-white p-3 rounded hover:bg-blue-700">
                إرسال كود التحقق
            </button>
        </form>
    </div>
</body>
</html>
"""

VERIFY_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>التحقق</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-lg shadow-md w-96 text-center">
        <h2 class="text-2xl font-bold mb-4 text-green-600">التحقق من الكود</h2>
        <p class="mb-4 text-gray-600">تم إرسال الكود إلى: {{ email }}</p>
        
        {% if error %}
        <div class="bg-red-100 text-red-700 p-2 mb-4 rounded">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <input type="number" name="otp" required placeholder="XXXX" 
                   class="w-full p-3 mb-4 border rounded text-center text-xl tracking-widest">
            <button type="submit" class="w-full bg-green-600 text-white p-3 rounded hover:bg-green-700">
                تفعيل الحساب
            </button>
        </form>
    </div>
</body>
</html>
"""

SUCCESS_HTML = """
<h1 style="text-align:center; color:green; margin-top:50px;">🎉 تم تفعيل الحساب بنجاح!</h1>
<p style="text-align:center;"><a href="/register">رجوع</a></p>
"""

# ================================
#      Routes
# ================================
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for('register'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        otp = random.randint(1000, 9999)

        # حفظ البيانات مؤقتاً
        session["temp_email"] = email
        session["temp_otp"] = str(otp)

        # طباعة الكود احتياطياً في السجلات
        print(f"🔑 [كود احتياطي] للإيميل {email} هو: {otp}")

        # محاولة الإرسال
        if send_email_logic(email, otp):
            return redirect(url_for('verify'))
        else:
            return "فشل إرسال الإيميل. راجع السجلات (Logs).", 500

    return render_template_string(REGISTER_HTML)

@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "temp_email" not in session:
        return redirect(url_for('register'))

    email = session["temp_email"]
    
    if request.method == "POST":
        user_code = request.form.get("otp", "").strip()
        correct_code = session.get("temp_otp")

        if user_code == correct_code:
            print(f"🎉 المستخدم {email} تم تفعيله!")
            session.pop("temp_otp", None) # مسح الكود بعد الاستخدام
            # هنا يمكنك حفظ المستخدم في قاعدة البيانات الحقيقية
            return render_template_string(SUCCESS_HTML)
        else:
            return render_template_string(VERIFY_HTML, email=email, error="الكود غير صحيح، حاول مرة أخرى.")

    return render_template_string(VERIFY_HTML, email=email)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
