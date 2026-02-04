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

# SECURE: No hardcoded credentials!
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

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

MIN_YES_PROB = 0.01
MAX_YES_PROB = 0.40
YES_PRICE_BUFFER_LOW = 500
YES_PRICE_BUFFER_HIGH = 600

MIN_NO_PROB = 0.70
MAX_NO_PROB = 0.99
NO_PRICE_BUFFER = 5000

MIN_PROFIT_THRESHOLD = 15

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets?active=true&closed=false"
ALERT_COOLDOWN = 3600
alerted_markets = {}

def get_current_btc_price():
    print("=== FETCHING BTC PRICE ===")
    
    try:
        print("Calling Binance API...")
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url, timeout=10)
        print("Binance response code: " + str(response.status_code))
        
        if response.status_code == 200:
            data = response.json()
            price = float(data['price'])
            print("*** Current BTC Price (Binance): $" + str(price) + " ***")
            return price
    except Exception as e:
        print("Binance failed: " + str(e))
    
    try:
        print("Trying CoinGecko API as backup...")
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            price = data['bitcoin']['usd']
            print("*** Current BTC Price (CoinGecko): $" + str(price) + " ***")
            return price
    except Exception as e:
        print("!!! Both APIs failed: " + str(e))
        return None

def extract_target_price(question):
    match = re.search(r"(\d{4,6})", question)
    if match:
        return int(match.group(1))
    return None

def extract_probabilities(outcomes):
    if not isinstance(outcomes, list):
        return None, None
    
    yes_prob = None
    no_prob = None
    
    for o in outcomes:
        if isinstance(o, dict):
            name = o.get("name", "").lower()
            try:
                price = float(o.get("price", 0))
                if name == "yes":
                    yes_prob = price
                elif name == "no":
                    no_prob = price
            except:
                pass
    
    return yes_prob, no_prob

def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

def calculate_profit(investment, probability):
    if probability <= 0:
        return 0
    payout = investment / probability
    profit = payout - investment
    return profit

def analyze_opportunity(current_btc, target_price, yes_prob, no_prob, is_above):
    if yes_prob is None or no_prob is None:
        return None
    
    distance = abs(target_price - current_btc)
    
    yes_alert = False
    yes_profit = calculate_profit(10, yes_prob)
    
    if MIN_YES_PROB <= yes_prob <= MAX_YES_PROB:
        if is_above:
            if YES_PRICE_BUFFER_LOW <= (target_price - current_btc) <= YES_PRICE_BUFFER_HIGH:
                yes_alert = True
        else:
            if YES_PRICE_BUFFER_LOW <= (current_btc - target_price) <= YES_PRICE_BUFFER_HIGH:
                yes_alert = True
    
    no_alert = False
    no_profit = calculate_profit(10, no_prob)
    
    if MIN_NO_PROB <= no_prob <= MAX_NO_PROB:
        if distance >= NO_PRICE_BUFFER:
            no_alert = True
    
    recommendation = None
    confidence = "LOW"
    
    if yes_alert and not no_alert:
        if yes_profit >= MIN_PROFIT_THRESHOLD:
            recommendation = "YES"
            if yes_profit >= 30:
                confidence = "HIGH"
            elif yes_profit >= 20:
                confidence = "MEDIUM"
    elif no_alert and not yes_alert:
        if no_profit >= 1:
            recommendation = "NO"
            confidence = "MEDIUM"
    elif yes_alert and no_alert:
        if yes_profit > no_profit * 5:
            recommendation = "YES"
            confidence = "MEDIUM"
        else:
            recommendation = "YES"
            confidence = "LOW"
    
    if recommendation:
        return {
            "recommendation": recommendation,
            "confidence": confidence,
            "yes_prob": yes_prob,
            "no_prob": no_prob,
            "yes_profit": yes_profit,
            "no_profit": no_profit,
            "distance": distance
        }
    
    return None

def bot_loop():
    print("=== STARTING BOT LOOP ===")
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping - couldn't fetch BTC price !!!")
            return
        
        markets = fetch_markets()
        print("Found " + str(len(markets)) + " total ACTIVE markets")
        
        bitcoin_count = 0
        alert_count = 0
        
        for m in markets:
            question = m.get("question", "")
            slug = m.get("slug", "")
            outcomes = m.get("outcomes", [])
            
            if "bitcoin" not in question.lower() and "btc" not in question.lower():
                continue
            
            bitcoin_count += 1
            
            if "above" not in question.lower() and "over" not in question.lower() and "below" not in question.lower() and "under" not in question.lower():
                print(">>> Bitcoin market (skipped - no direction): " + question[:60])
                continue
            
            is_above_market = "above" in question.lower() or "over" in question.lower()
            
            yes_prob, no_prob = extract_probabilities(outcomes)
            target_price = extract_target_price(question)
            
            print(">>> Bitcoin market: " + question[:80])
            print("    YES: " + str(yes_prob) + " | NO: " + str(no_prob) + " | Target: $" + str(target_price))
            
            if yes_prob is None or no_prob is None or target_price is None:
                print("    SKIP: Missing data")
                continue
            
            opportunity = analyze_opportunity(current_btc_price, target_price, yes_prob, no_prob, is_above_market)
            
            if opportunity:
                current_time = time.time()
                if slug in alerted_markets:
                    time_since_alert = current_time - alerted_markets[slug]
                    if time_since_alert < ALERT_COOLDOWN:
                        print("    SKIP: Already alerted " + str(int(time_since_alert/60)) + " minutes ago")
                        continue
                
                print("    !!! SENDING SMART ALERT !!!")
                alerted_markets[slug] = current_time
                
                rec = opportunity["recommendation"]
                conf = opportunity["confidence"]
                yes_p = opportunity["yes_prob"]
                no_p = opportunity["no_prob"]
                yes_profit = opportunity["yes_profit"]
                no_profit = opportunity["no_profit"]
                distance = opportunity["distance"]
                
                direction = "above" if is_above_market else "below"
                
                message = "🎯 POLYMARKET SMART ALERT\n\n"
                message += "📊 Market: " + question + "\n\n"
                message += "🎯 Target: $" + str(target_price) + "\n"
                message += "💰 Current BTC: $" + str(int(current_btc_price)) + "\n"
                message += "📏 Distance: $" + str(int(distance)) + "\n\n"
                
                message += "PROBABILITY ANALYSIS:\n"
                message += "├─ YES @ " + str(int(yes_p * 100)) + "% → Win: +$" + str(round(yes_profit, 2)) + " | Lose: -$10\n"
                message += "└─ NO @ " + str(int(no_p * 100)) + "% → Win: +$" + str(round(no_profit, 2)) + " | Lose: -$10\n\n"
                
                if rec == "YES":
                    message += "🧠 SMART RECOMMENDATION: BUY YES ✅\n"
                    message += "📈 Confidence: " + conf + "\n"
                    message += "💡 Why? BTC is $" + str(int(distance)) + " from target. "
                    if yes_p < 0.20:
                        message += str(int(yes_p * 100)) + "% seems undervalued!\n"
                    else:
                        message += "Good potential profit!\n"
                else:
                    message += "🧠 SMART RECOMMENDATION: BUY NO ✅\n"
                    message += "📈 Confidence: " + conf + "\n"
                    message += "💡 Why? BTC is $" + str(int(distance)) + " away. "
                    message += "Very unlikely to reach target. Safe bet!\n"
                
                message += "\n🔗 https://polymarket.com/market/" + slug
                
                if send_alert(message):
                    alert_count += 1
                    print("    SMART ALERT SENT!")
            else:
                print("    No opportunity found")
        
        print("=== Check complete. Bitcoin markets: " + str(bitcoin_count) + ", Alerts sent: " + str(alert_count) + " ===")
        
    except Exception as e:
        print("!!! ERROR in bot_loop: " + str(e))
        import traceback
        traceback.print_exc()

def run_bot():
    print("=== WORKER BOOTED - SMART MODE ===")
    
    startup_msg = "🚀 Polymarket SMART BOT is LIVE!\n\n"
    startup_msg += "🧠 Mode: Smart Analysis (YES + NO)\n"
    startup_msg += "✅ Price: Binance (CoinGecko backup)\n"
    startup_msg += "✅ Check: Every 60 seconds\n"
    startup_msg += "✅ YES range: 1%-40% probability\n"
    startup_msg += "✅ NO range: 70%-99% probability\n"
    startup_msg += "✅ Alert distance: $500-$600 from target\n\n"
    startup_msg += "💡 Bot will recommend YES or NO based on best value!"
    
    if send_alert(startup_msg):
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
