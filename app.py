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

TRUSTED_SOURCES = [
    "reuters.com", "bbc.com", "cnn.com", "aljazeera.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "who.int",
    "bloomberg.com", "aljazeera.net", "alarabiya.net", "skynewsarabia.com",
    "youm7.com", "masrawy.com", "shorouknews.com", "independentarabia.com",
    "bbc.com/arabic", "al-ain.com", "kooora.com", "yallakora.com"
]

FACT_CHECKERS = [
    "snopes.com", "politifact.com", "factcheck.org",
    "fullfact.org", "fatabyyano.net", "misbar.com", "dabegad.com"
]

# ==========================================
# 🗄️ Database Helpers
# ==========================================
DB_FILE = "local_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": [], "news": [], "history": [], "reports": []}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in ["history", "reports"]:
                if key not in data:
                    data[key] = []
            return data
    except:
        return {"users": [], "news": [], "history": [], "reports": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(username):
    db = load_db()
    return next((u for u in db['users'] if u['username'] == username), None)

# ==========================================
# ✅ DEMO ACCOUNT (AUTO CREATED)
# ==========================================
DEMO_USER = {
    "username": "emam73477",
    "email": "emam73477@gmail.com",
    "password": generate_password_hash("Abohamid.123"),
    "created_at": str(datetime.datetime.now())
}

def get_user(identifier):
    db = load_db()
    return next(
        (
            u for u in db['users']
            if u['username'] == identifier or u['email'] == identifier
        ),
        None
    )


# ==========================================
# 🧠 AI Core
# ==========================================
def analyze_news_logic(text, lang="ar"):
    url = "https://google.serper.dev/search"
    tbs_param = ""
    time_sensitive = False

    if lang == 'ar':
        search_query = f"{text} حقيقة"
        LBL_REAL, LBL_FAKE, LBL_UNSURE = "خبر حقيقي", "خبر زائف", "غير مؤكد"
        NEGATIONS = ["خدعة", "كذب", "إشاعة", "نفي", "مفبرك", "غير صحيح", "شائعة"]
        if any(w in text for w in ["أمس", "امس", "اليوم", "عاجل"]):
            tbs_param = "qdr:d2"
            time_sensitive = True
    else:
        search_query = f"{text} truth"
        LBL_REAL, LBL_FAKE, LBL_UNSURE = "REAL", "FAKE", "UNVERIFIED"
        NEGATIONS = ["hoax", "fake", "rumor", "false", "debunked"]

    payload = {"q": search_query, "gl": "eg", "hl": lang}
    if tbs_param:
        payload["tbs"] = tbs_param

    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        results = data.get("organic", [])

        if not results:
            return {"verdict": LBL_UNSURE, "score": 50, "reasons": ["لا توجد نتائج كافية"], "sources": []}

        score = 50
        reasons = []
        sources = []

        for r in results:
            link = r.get("link", "").lower()
            content = (r.get("title", "") + r.get("snippet", "")).lower()

            if any(n in content for n in NEGATIONS):
                score -= 25
            if any(t in link for t in TRUSTED_SOURCES):
                score += 20
                sources.append({"title": r.get("title"), "link": link})

        if score >= 80:
            verdict = LBL_REAL
        elif score <= 35:
            verdict = LBL_FAKE
        else:
            verdict = LBL_UNSURE

        return {
            "verdict": verdict,
            "score": max(0, min(score, 100)),
            "reasons": reasons[:2],
            "sources": sources[:5]
        }
    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "reasons": [str(e)], "sources": []}

# ==========================================
# 🌐 Routes
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_user(request.form['username'])
        if user and check_password_hash(user['password'], request.form['password']):
            session['user'] = user['username']
            return redirect(url_for('home'))
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    result = analyze_news_logic(data.get('text', ''), data.get('lang', 'ar'))
    return jsonify(result)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)






