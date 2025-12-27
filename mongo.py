import os
from pymongo import MongoClient

# 1. الرابط الرسمي (نظيف تماماً كما في تعليمات مونجو)
# استبدل <password> بكلمة مرورك: Abohamid.123
MONGO_URI = "mongodb+srv://emammohammed605_db_user:Abohamid.123@cluster0.dumu7fi.mongodb.net/?appName=Cluster0"

# 2. إنشاء الاتصال
try:
    client = MongoClient(MONGO_URI)
    # نحدد قاعدة البيانات والمجموعة
    db = client["media_db"] 
    news_collection = db["news"]
    
    # اختبار بسيط للاتصال
    client.admin.command('ping')
    print("✅ تم الاتصال بنجاح باستخدام الطريقة الرسمية!")
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")
    news_collection = None
