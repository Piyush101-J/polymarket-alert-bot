import time
import requests
import re
from threading import Thread
from flask import Flask
import os
from datetime import datetime, timezone
import json

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
MAX_YES_PROB = 0.42
YES_PRICE_BUFFER_LOW = 1500
YES_PRICE_BUFFER_HIGH = 4500

MIN_NO_PROB = 0.70
MAX_NO_PROB = 0.99
NO_PRICE_BUFFER = 5000

MIN_PROFIT_THRESHOLD = 15

ALERT_COOLDOWN = 3600
alerted_markets = {}

# ADD ALL YOUR MARKET URLS HERE - BOT WILL AUTO-SKIP EXPIRED ONES!
MONITORED_MARKETS = [
    # February markets
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-66k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-68k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-68k-on-february-8",
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-70k-on-february-8",
    "https://polymarket.com/event/bitcoin-above-on-february-9/bitcoin-above-72k-on-february-9",
    "https://polymarket.com/event/bitcoin-above-on-february-7/bitcoin-above-70k-on-february-7",
    
    # Add more URLs here - old ones will be auto-skipped!
]

def get_current_btc_price():
    print("=== FETCHING BTC PRICE ===")
    
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = float(data['price'])
            print("*** BTC Price (Binance): $" + str(price) + " ***")
            return price
    except Exception as e:
        print("Binance failed: " + str(e))
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = float(data['bitcoin']['usd'])
            print("*** BTC Price (CoinGecko): $" + str(price) + " ***")
            return price
    except Exception as e:
        print("CoinGecko failed: " + str(e))
    
    try:
        url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = float(data['data']['amount'])
            print("*** BTC Price (Coinbase): $" + str(price) + " ***")
            return price
    except Exception as e:
        print("Coinbase failed: " + str(e))
    
    try:
        url = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'result' in data and 'XXBTZUSD' in data['result']:
                price = float(data['result']['XXBTZUSD']['c'][0])
                print("*** BTC Price (Kraken): $" + str(price) + " ***")
                return price
    except Exception as e:
        print("Kraken failed: " + str(e))
    
    print("!!! ALL PRICE APIs FAILED !!!")
    return None

def extract_market_slug(url):
    """Extract market slug from Polymarket URL"""
    parts = url.rstrip('/').split('/')
    return parts[-1]

def extract_target_price(question):
    patterns = [
        r'\$?(\d{1,3}),?(\d{3})',
        r'(\d{5,6})',
        r'(\d{2,3})k',
        r'\$(\d{2,3})k'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            if 'k' in question.lower():
                num = match.group(1)
                return int(num) * 1000
            elif len(match.groups()) > 1 and match.group(2):
                return int(match.group(1) + match.group(2))
            else:
                num = match.group(1)
                if len(num) >= 4:
                    return int(num)
    return None

def extract_probabilities(market):
    outcomes = market.get("outcomes", [])
    if isinstance(outcomes, list) and len(outcomes) > 0:
        for o in outcomes:
            if isinstance(o, dict):
                name = o.get("name", "").lower()
                try:
                    price = float(o.get("price", 0))
                    if name == "yes":
                        return price, 1 - price
                except:
                    pass
    
    outcomes_str = market.get("outcomes")
    prices_str = market.get("outcomePrices")
    
    if outcomes_str and prices_str:
        try:
            if isinstance(outcomes_str, str):
                outcomes_list = json.loads(outcomes_str)
            else:
                outcomes_list = outcomes_str
            
            if isinstance(prices_str, str):
                prices_list = json.loads(prices_str)
            else:
                prices_list = prices_str
            
            for i, outcome in enumerate(outcomes_list):
                if i < len(prices_list):
                    name = str(outcome).lower()
                    price = float(prices_list[i])
                    
                    if name == "yes":
                        yes_prob = price
                        no_prob = 1 - price
                        return yes_prob, no_prob
            
            if len(prices_list) >= 2:
                yes_prob = float(prices_list[0])
                no_prob = float(prices_list[1])
                return yes_prob, no_prob
                
        except Exception as e:
            print("    Error parsing outcomes: " + str(e))
    
    return None, None

def is_market_expired_or_resolved(market):
    """Check if market is expired, closed, or resolved"""
    try:
        # Check if market is closed
        if market.get("closed", False):
            return True
        
        # Check if market is resolved
        if market.get("resolved", False):
            return True
        
        # Check end date
        end_date = market.get("end_date_iso") or market.get("endDate") or market.get("end_date") or market.get("endDateIso")
        if not end_date:
            return False
        
        current_time = datetime.now(timezone.utc)
        
        if isinstance(end_date, str):
            end_date_clean = end_date.replace('Z', '+00:00')
            try:
                end_dt = datetime.fromisoformat(end_date_clean)
            except:
                try:
                    end_dt = datetime.fromtimestamp(float(end_date), tz=timezone.utc)
                except:
                    return False
        elif isinstance(end_date, (int, float)):
            end_dt = datetime.fromtimestamp(end_date, tz=timezone.utc)
        else:
            return False
        
        # Market is expired if end date has passed
        return end_dt < current_time
    except Exception as e:
        print(f"    Error checking expiry: {e}")
        return False

def fetch_market_by_slug(slug):
    """Fetch a specific market by its slug"""
    try:
        url = f"https://gamma-api.polymarket.com/markets/{slug}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"    Market returned status {response.status_code}")
            return None
    except Exception as e:
        print(f"    Error fetching market: {e}")
        return None

def calculate_profit(investment, probability):
    if probability <= 0:
        return 0
    payout = investment / probability
    profit = payout - investment
    return profit

def analyze_opportunity(current_btc, target_price, yes_prob, no_prob):
    if yes_prob is None or no_prob is None:
        return None
    
    distance = abs(target_price - current_btc)
    actual_distance = target_price - current_btc
    
    yes_alert = False
    yes_profit = calculate_profit(10, yes_prob)
    
    if MIN_YES_PROB <= yes_prob <= MAX_YES_PROB:
        if YES_PRICE_BUFFER_LOW <= actual_distance <= YES_PRICE_BUFFER_HIGH:
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
            print("!!! Skipping - no BTC price !!!")
            return
        
        print(f"\n=== CHECKING {len(MONITORED_MARKETS)} MARKETS ===\n")
        
        alert_count = 0
        active_count = 0
        expired_count = 0
        
        for market_url in MONITORED_MARKETS:
            slug = extract_market_slug(market_url)
            
            print(f">>> Checking: {slug}")
            
            market = fetch_market_by_slug(slug)
            
            if not market:
                print(f"    SKIP: Could not fetch (might be deleted)")
                continue
            
            # CHECK IF EXPIRED/RESOLVED
            if is_market_expired_or_resolved(market):
                expired_count += 1
                print(f"    SKIP: Market expired/resolved ⏰")
                continue
            
            active_count += 1
            
            question = market.get("question", "")
            
            yes_prob, no_prob = extract_probabilities(market)
            target_price = extract_target_price(question)
            
            print(f"    ✅ ACTIVE: {question[:50]}")
            print(f"    YES: {yes_prob} | NO: {no_prob}")
            print(f"    Target: ${target_price}")
            
            if yes_prob is None or no_prob is None:
                print("    SKIP: No probability")
                continue
            
            if target_price is None:
                print("    SKIP: No target")
                continue
            
            dist = target_price - current_btc_price
            
            print(f"    Distance: ${dist}")
            print(f"    In range ($1500-$4500)? {YES_PRICE_BUFFER_LOW <= dist <= YES_PRICE_BUFFER_HIGH}")
            print(f"    Prob in range (1%-42%)? {MIN_YES_PROB <= yes_prob <= MAX_YES_PROB}")
            
            opportunity = analyze_opportunity(current_btc_price, target_price, yes_prob, no_prob)
            
            if opportunity:
                current_time = time.time()
                if slug in alerted_markets:
                    time_since = current_time - alerted_markets[slug]
                    if time_since < ALERT_COOLDOWN:
                        print(f"    SKIP: Already alerted {int(time_since/60)} min ago")
                        continue
                
                print("    *** SENDING ALERT! ***")
                alerted_markets[slug] = current_time
                
                rec = opportunity["recommendation"]
                conf = opportunity["confidence"]
                yes_p = opportunity["yes_prob"]
                no_p = opportunity["no_prob"]
                yes_profit = opportunity["yes_profit"]
                no_profit = opportunity["no_profit"]
                distance = opportunity["distance"]
                
                message = "🎯 POLYMARKET OPPORTUNITY!\n\n"
                message += f"📊 {question}\n\n"
                message += f"🎯 Target: ${target_price:,}\n"
                message += f"💰 Current BTC: ${int(current_btc_price):,}\n"
                message += f"📏 Distance: ${int(distance):,}\n\n"
                
                message += "ANALYSIS:\n"
                message += f"├─ YES @ {int(yes_p * 100)}% → Profit: +${round(yes_profit, 2)}\n"
                message += f"└─ NO @ {int(no_p * 100)}% → Profit: +${round(no_profit, 2)}\n\n"
                
                if rec == "YES":
                    message += "🧠 RECOMMENDATION: BUY YES ✅\n"
                    message += f"📈 Confidence: {conf}\n"
                    message += f"💡 ${int(distance):,} from target"
                else:
                    message += "🧠 RECOMMENDATION: BUY NO ✅\n"
                    message += f"📈 Confidence: {conf}"
                
                message += f"\n\n🔗 {market_url}"
                
                if send_alert(message):
                    alert_count += 1
                    print("    ✅ ALERT SENT!")
            else:
                print("    No opportunity (outside criteria)")
        
        print(f"\n=== SUMMARY ===")
        print(f"Total URLs: {len(MONITORED_MARKETS)}")
        print(f"Active Markets: {active_count} ✅")
        print(f"Expired/Resolved: {expired_count} ⏰")
        print(f"Alerts Sent: {alert_count} 🔔")
        print(f"===============\n")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def run_bot():
    print("=== BOT v14 FINAL - SMART DATE FILTERING ===")
    print(f"Monitoring {len(MONITORED_MARKETS)} URLs")
    print("Old/expired markets will be auto-skipped!")
    
    startup_msg = "🎯 Bot v14 FINAL is LIVE!\n\n"
    startup_msg += f"✅ Monitoring {len(MONITORED_MARKETS)} market URLs\n"
    startup_msg += "✅ Auto-skips expired markets ⏰\n"
    startup_msg += "✅ No need to remove old URLs!\n"
    startup_msg += "✅ Settings: 1-42%, $1,500-$4,500\n\n"
    startup_msg += "Just add new URLs - bot handles the rest!"
    
    if send_alert(startup_msg):
        print("✅ Startup message sent!")
    
    while True:
        try:
            bot_loop()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    from waitress import serve
    
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    serve(app, host="0.0.0.0", port=port)
