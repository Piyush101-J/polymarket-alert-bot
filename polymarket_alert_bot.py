import time
import requests
import re
from threading import Thread
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running", 200

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/test')
def test():
    success = send_alert("Manual test from test endpoint")
    return "Message sent: {}".format(success), 200

BOT_TOKEN = "8534636585:AAHGUIe4wVSiRx1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

def send_alert(text):
    url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram response: {} - {}".format(response.status_code, response.text))
        return response.status_code == 200
    except Exception as e:
        print("Failed to send alert: {}".format(e))
        return False

CHECK_INTERVAL = 60
MIN_PROB = 0.01
MAX_PROB = 0.40
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

def extract_target_price(question):
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

def bot_loop():
    print("Checking markets...")
    try:
        markets = fetch_markets()
        print("Found {} markets".format(len(markets)))
        
        bitcoin_count = 0
        alert_count = 0
        
        for m in markets:
            question = m.get("question", "")
            slug = m.get("slug", "")
            outcomes = m.get("outcomes", [])
            
            if "bitcoin" not in question.lower():
                continue
            
            bitcoin_count += 1
            prob = extract_yes_probability(outcomes)
            target_price = extract_target_price(question)
            
            print("Bitcoin market: {}... | Prob: {} | Target: {}".format(question[:50], prob, target_price))
            
            if prob is None or target_price is None:
                continue
            
            if MIN_PROB <= prob <= MAX_PROB:
                url = "https://polymarket.com/market/{}".format(slug)
                message = "EARLY POLYMARKET ALERT\n\nQuestion: {}\nTarget Price: {}\nYES Probability: {:.2f}%\nLink: {}".format(question, target_price, prob*100, url)
                if send_alert(message):
                    alert_count += 1
                    print("Alert sent for: {}...".format(question[:50]))
        
        print("Check complete. Bitcoin markets: {}, Alerts sent: {}".format(bitcoin_count, alert_count))
        
    except Exception as e:
        print("Error in bot_loop: {}".format(e))

def run_bot():
    print("Worker booted, running permanently")
    
    if send_alert("Polymarket BTC Alert Bot is LIVE"):
        print("Startup message sent successfully!")
    else:
        print("Failed to send startup message - CHECK YOUR BOT_TOKEN AND CHAT_ID!")
    
    while True:
        try:
            bot_loop()
        except Exception as e:
            print("Error: {}".format(e))
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    from waitress import serve
    
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 8080))
    print("Starting server on port {}".format(port))
    serve(app, host="0.0.0.0", port=port)
