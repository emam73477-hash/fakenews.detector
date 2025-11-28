from pymongo import MongoClient
import urllib.parse
import certifi

# 1. Credentials
username = urllib.parse.quote_plus("Mohamed")
password = urllib.parse.quote_plus("@Abohamid.123")

# 2. Connection URI
uri = f"mongodb+srv://{username}:{password}@cluster0.x87bvlf.mongodb.net/news_verification?retryWrites=true&w=majority&appName=Cluster0"

db = None
users_collection = None
news_collection = None

try:
    print("☁️ Connecting to Cloud Database (MongoDB Atlas)...")
    
    # --- THE FIX IS HERE ---
    # We added 'tlsDisableOCSPEndpointCheck=True'
    client = MongoClient(uri, 
                         tlsCAFile=certifi.where(),
                         tlsAllowInvalidCertificates=True,
                         tlsDisableOCSPEndpointCheck=True) 
    
    # Test connection
    client.admin.command('ping')
    print("✅ SUCCESS: Connected to Cloud Database!")
    
    db = client.news_verification
    users_collection = db.users
    news_collection = db.news_articles

except Exception as e:
    print("❌ CLOUD ERROR: Could not connect (Running in Offline Mode).")
    print(f"Details: {e}")