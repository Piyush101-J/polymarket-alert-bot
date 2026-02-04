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
    price = get_current_btc_price()
    return "BTC Price: $" + str(price), 200

BOT_TOKEN = "8534636585:AAHGUIe4wVSiRx1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

def send_alert(text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram response: " + str(response.status_code))
        return response.status_code == 200
    except Exception as e:
        print("Failed to send alert: " + str(e))
        return False

CHECK_INTERVAL = 60
MIN_PROB = 0.01
MAX_PROB = 0.40
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"
PRICE_BUFFER_LOW = 500
PRICE_BUFFER_HIGH = 600

def get_current_btc_price():
    print("=== FETCHING BTC PRICE ===")
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        print("Calling CoinGecko API...")
        response = requests.get(url, timeout=10)
        print("CoinGecko response code: " + str(response.status_code))
        data = response.json()
        print("CoinGecko response data: " + str(data))
        price = data['bitcoin']['usd']
        print("*** Current BTC Price: $" + str(price) + " ***")
        return price
    except Exception as e:
        print("!!! ERROR fetching BTC price: " + str(e))
        return None

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

def is_price_in_range(current_price, target_price):
    if current_price is None or target_price is None:
        print("Price check failed: current=" + str(current_price) + " target=" + str(target_price))
        return False
    
    lower_bound = target_price - PRICE_BUFFER_HIGH
    upper_bound = target_price - PRICE_BUFFER_LOW
    
    in_range = lower_bound <= current_price <= upper_bound
    
    print("Price check: $" + str(current_price) + " vs range $" + str(lower_bound) + "-$" + str(upper_bound) + " = " + str(in_range))
    
    return in_range

def bot_loop():
    print("=== STARTING BOT LOOP ===")
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping - couldn't fetch BTC price !!!")
            return
        
        markets = fetch_markets()
        print("Found " + str(len(markets)) + " total markets")
        
        bitcoin_count = 0
        alert_count = 0
        
        for m in markets:
            question = m.get("question", "")
            slug = m.get("slug", "")
            outcomes = m.get("outcomes", [])
            
            if "bitcoin" not in question.lower():
                continue
            
            if "above" not in question.lower() and "over" not in question.lower():
                continue
            
            bitcoin_count += 1
            prob = extract_yes_probability(outcomes)
            target_price = extract_target_price(question)
            
            print(">>> Bitcoin market: " + question[:60])
            print("    Probability: " + str(prob))
            print("    Target: $" + str(target_price))
            
            if prob is None or target_price is None:
                print("    SKIP: Missing prob or target")
                continue
            
            if MIN_PROB <= prob <= MAX_PROB:
                print("    Probability is in range!")
                if is_price_in_range(current_btc_price, target_price):
                    print("    !!! SENDING ALERT !!!")
                    url = "https://polymarket.com/market/" + slug
                    message = "CRITICAL ALERT - BTC APPROACHING TARGET\n\n"
                    message += "Question: " + question + "\n"
                    message += "Target Price: $" + str(target_price) + "\n"
                    message += "Current BTC Price: $" + str(current_btc_price) + "\n"
                    message += "Distance to Target: $" + str(target_price - current_btc_price) + "\n"
                    message += "YES Probability: " + str(round(prob * 100, 2)) + "%\n"
                    message += "Link: " + url
                    
                    if send_alert(message):
                        alert_count += 1
                        print("    ALERT SENT!")
            else:
                print("    SKIP: Probability " + str(prob) + " not in range " + str(MIN_PROB) + "-" + str(MAX_PROB))
        
        print("=== Check complete. Bitcoin markets: " + str(bitcoin_count) + ", Alerts sent: " + str(alert_count) + " ===")
        
    except Exception as e:
        print("!!! ERROR in bot_loop: " + str(e))
        import traceback
        traceback.print_exc()

def run_bot():
    print("=== WORKER BOOTED ===")
    
    if send_alert("Polymarket BTC Alert Bot is LIVE - Price Checking Enabled"):
        print("Startup message sent!")
    else:
        print("Failed to send startup message")
    
    while True:
        try:
            bot_loop()
        except Exception as e:
            print("Error: " + str(e))
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    from waitress import serve
    
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 8080))
    print("Starting server on port " + str(port))
    serve(app, host="0.0.0.0", port=port)
