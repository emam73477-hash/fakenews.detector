import os
import json
import random
import datetime
import threading
import requests
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "competition_secret")

# ==========================================
# 🔑 API KEYS
# ==========================================
BREVO_API_KEY = os.environ.get("MAIL_PASSWORD")
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "YOUR_SERPER_KEY_HERE")

# ==========================================
# 🌍 Trusted Sources
# ==========================================
TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int", "bloomberg.com",
    "aljazeera.net", "alarabiya.net", "skynewsarabia.com", "youm7.com",
    "masrawy.com", "shorouknews.com", "independentarabia.com", "bbc.com/arabic"
]

FACT_CHECKERS = [
    "snopes.com", "politifact.com", "factcheck.org", "fullfact.org",
    "fatabyyano.net", "misbar.com", "dabegad.com"
]

# ==========================================
# 🗄️ Local DB
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": []}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(username):
    for user in load_db()["users"]:
        if user["username"] == username:
            return user
    return None

def create_user(user_data):
    db = load_db()
    db["users"].append(user_data)
    save_db(db)

# ==========================================
# 📧 Email
# ==========================================
def send_email_logic(receiver_email, otp):
    if not BREVO_API_KEY or not SENDER_EMAIL:
        return
    requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        },
        json={
            "sender": {"name": "FakeNews Detector", "email": SENDER_EMAIL},
            "to": [{"email": receiver_email}],
            "subject": "Verification Code",
            "htmlContent": f"<h2>Your code: {otp}</h2>"
        }
    )

# ==========================================
# 🛑 Text Validation
# ==========================================
def is_meaningful_text(text):
    words = text.strip().split()
    if len(words) < 4:
        return False, "Text must be more than 3 words"

    letters = sum(c.isalpha() for c in text)
    if letters / max(len(text), 1) < 0.6:
        return False, "Text contains too many symbols"

    if len(set(text)) < len(text) * 0.2:
        return False, "Text is not meaningful"

    return True, ""

# ==========================================
# 🧠 AI CORE
# ==========================================
def analyze_news_logic(text, lang="en"):
    payload = {
        "q": text,
        "gl": "eg" if lang == "ar" else "us",
        "hl": lang
    }

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://google.serper.dev/search",
        headers=headers,
        json=payload,
        timeout=10
    )

    data = response.json()
    results = data.get("organic", [])

    score = 50
    sources = []
    reasons = []
    dates = []

    if not results:
        return {
            "verdict": "FAKE" if lang == "en" else "خبر زائف",
            "score": 0,
            "date_info": "N/A",
            "reasons": ["No results found"],
            "sources": []
        }

    for r in results:
        link = r.get("link", "")
        title = r.get("title", "")
        date = r.get("date")

        if date:
            dates.append(date)

        for t in TRUSTED_SOURCES:
            if t in link:
                score += 20
                sources.append({"title": title, "link": link, "type": "Trusted"})

        for f in FACT_CHECKERS:
            if f in link:
                score -= 30
                sources.append({"title": title, "link": link, "type": "Fact Check"})
                reasons.append(f"Flagged by {f}")

    # 🧠 Final verdict
    if score >= 80 and sources:
        verdict = "REAL" if lang == "en" else "خبر حقيقي"
    elif score <= 30:
        verdict = "FAKE" if lang == "en" else "خبر زائف"
    else:
        verdict = "UNVERIFIED" if lang == "en" else "غير مؤكد"

    first_seen = min(dates) if dates else "Date unavailable"

    return {
        "verdict": verdict,
        "score": min(score, 100),
        "date_info": first_seen,
        "reasons": list(set(reasons)),
        "sources": sources[:5]
    }

# ==========================================
# 🌐 ROUTES
# ==========================================
@app.route("/analyze", methods=["POST"])
def analyze():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    text = data.get("text", "")
    lang = data.get("lang", "en")

    ok, msg = is_meaningful_text(text)
    if not ok:
        return jsonify({
            "verdict": "INVALID",
            "score": 0,
            "reasons": [msg],
            "sources": []
        }), 400

    return jsonify(analyze_news_logic(text, lang))

# ==========================================
# 🔐 AUTH
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        otp = str(random.randint(1000, 9999))
        threading.Thread(
            target=send_email_logic,
            args=(request.form["email"], otp)
        ).start()

        session["otp"] = otp
        session["temp_user"] = {
            "username": request.form["username"],
            "email": request.form["email"],
            "password": generate_password_hash(request.form["password"])
        }
        return redirect(url_for("verify_otp"))
    return render_template("register.html")

@app.route("/verify", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        if request.form["otp"] == session.get("otp"):
            create_user(session["temp_user"])
            session["user"] = session["temp_user"]["username"]
            session.pop("temp_user")
            return redirect(url_for("home"))
    return render_template("verify.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_user(request.form["username"])
        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["username"]
            return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ==========================================
# ▶️ RUN
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

