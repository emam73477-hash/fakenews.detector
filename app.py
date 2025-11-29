import os
import smtplib
import random
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

SENDER_EMAIL = os.getenv("MAIL_USERNAME")
SENDER_PASSWORD = os.getenv("MAIL_PASSWORD")   # API KEY من Brevo

# ================================
#  دالة إرسال الإيميل (BREVO SMTP)
# ================================
def send_email_logic(receiver_email, otp):
    print(f"\n🔄 [بدء الإرسال] محاولة إرسال كود {otp} إلى: {receiver_email}")

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ [خطأ] MAIL_USERNAME أو MAIL_PASSWORD غير موجودين في Render!")
        return False

    msg = MIMEText(f"مرحباً،\n\nكود التفعيل الخاص بك هو: {otp}\n\nشكراً لك.")
    msg['Subject'] = "Verification Code"
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email

    try:
        # SMTP الخاص بـ BREVO
        with smtplib.SMTP("smtp-relay.brevo.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())

        print(f"✅ تم إرسال الكود إلى {receiver_email}")
        return True

    except Exception as e:
        print(f"❌ فشل الإرسال: {e}")
        return False


# ================================
#      صفحة التسجيل
# ================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        otp = random.randint(1000, 9999)

        session["email"] = email
        session["otp"] = otp

        print(f"🔑 [كود احتياطي] للمستخدم {email} هو: {otp}")

        if send_email_logic(email, otp):
            return redirect("/verify")
        else:
            return "حدث خطأ أثناء إرسال الإيميل. تأكد من إعداد Brevo.", 500

    return render_template("register.html")


# ================================
#      صفحة التحقق
# ================================
@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "otp" not in session:
        return redirect("/register")

    if request.method == "POST":
        user_code = request.form["otp"]

        if str(user_code) == str(session["otp"]):
            email = session["email"]
            print(f"🎉 المستخدم {email} تم تفعيله بنجاح!")
            return "تم التحقق بنجاح 🎉"

        return "الكود غير صحيح!"

    return render_template("verify.html")


# ================================
#      تشغيل التطبيق
# ================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

