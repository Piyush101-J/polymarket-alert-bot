import time
import requests
import re
from threading import Thread
from flask import Flask
import os

# ================= FLASK HEALTH CHECK =================
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running", 200

@app.route('/health')
def health_check():
    return "OK", 200

# ================= TELEGRAM =================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

def send_alert(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send alert: {e}")

# ================= SETTINGS =================
CHECK_INTERVAL = 60        # seconds
MIN_PROB = 0.01            # 1%
MAX_PROB = 0.40            # 40%
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

# ================= HELPERS =================
def extract_target_price(question: str):
    """
    Extracts price like 80000 from:
    'Bitcoin above 80000 on February 4?'
    """
    match = re.search(r"(\d{4,6})", question)
    if match:
        return int(match.group(1))
    return None

def extract_yes_probability(outcomes):
    if not isinstance(outcomes, list):
        return None
    for o in outcomes:
        if isinstance(o, dict) and o.get("name", "").lower() == "yes":
            try:
                return float(o.get("price"))
            except:
                return None
    return None

def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

# ================= CORE LOOP =================
def bot_loop():
    markets = fetch_markets()
    for m in markets:
        question = m.get("question", "")
        slug = m.get("slug", "")
        outcomes = m.get("outcomes", [])
        
        if "bitcoin" not in question.lower():
            continue
        
        prob = extract_yes_probability(outcomes)
        target_price = extract_target_price(question)
        
        if prob is None or target_price is None:
            continue
        
        if MIN_PROB <= prob <= MAX_PROB:
            url = f"https://polymarket.com/market/{slug}"
            message = (
                f"🚨 EARLY POLYMARKET ALERT\n\n"
                f"🪙 {question}\n"
                f"🎯 Target Price: {target_price}\n"
                f"📊 YES Probability: {prob*100:.2f}%\n"
                f"🔗 {url}"
            )
            send_alert(message)

def run_bot():
    """Background thread for bot logic"""
    print("🚀 Worker booted, running permanently")
    send_alert("🚀 Polymarket BTC Alert Bot is LIVE")
    
    while True:
        try:
            bot_loop()
        except Exception as e:
            print(f"Error in bot loop: {e}")
        time.sleep(CHECK_INTERVAL)

# ================= BOOTSTRAP =================
if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask server (keeps Railway happy)
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Flask server on port {port}")
    app.run(host="0.0.0.0", port=port)
```

**Also create/update your `requirements.txt` file:**
```
requests
flask
