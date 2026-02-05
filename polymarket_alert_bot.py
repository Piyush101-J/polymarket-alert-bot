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
            
            if yes_prob is None and no_prob is None:
                try:
                    prob = float(o.get("probability", 0))
                    if name == "yes":
                        yes_prob = prob
                    elif name == "no":
                        no_prob = prob
                except:
                    pass
    
    return yes_prob, no_prob

def is_market_expired(market):
    try:
        if market.get("closed", False):
            return True
        
        end_date = market.get("end_date_iso") or market.get("endDate") or market.get("end_date")
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
        
        return end_dt < current_time
    except Exception as e:
        return False

def fetch_markets_and_events():
    all_markets = []
    seen_slugs = set()
    
    print("=== FETCHING MARKETS AND EVENTS ===")
    
    try:
        print("Fetching regular markets...")
        url = "https://gamma-api.polymarket.com/markets?limit=200&closed=false"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        markets = response.json()
        
        for m in markets:
            slug = m.get("slug", "")
            if not slug or slug in seen_slugs:
                continue
            if is_market_expired(m):
                continue
            all_markets.append(m)
            seen_slugs.add(slug)
        
        print("Got " + str(len(all_markets)) + " regular markets")
    except Exception as e:
        print("Error fetching regular markets: " + str(e))
    
    try:
        print("Fetching EVENTS...")
        url = "https://gamma-api.polymarket.com/events?limit=100&closed=false"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        events = response.json()
        
        print("Got " + str(len(events)) + " events")
        
        event_market_count = 0
        for event in events:
            markets_in_event = event.get("markets", [])
            
            for m in markets_in_event:
                slug = m.get("slug", "")
                if not slug or slug in seen_slugs:
                    continue
                if is_market_expired(m):
                    continue
                
                event_title = event.get("title", "")
                if event_title:
                    m["event_title"] = event_title
                
                all_markets.append(m)
                seen_slugs.add(slug)
                event_market_count += 1
        
        print("Extracted " + str(event_market_count) + " markets from events")
    except Exception as e:
        print("Error fetching events: " + str(e))
    
    print("=== TOTAL: " + str(len(all_markets)) + " ===")
    return all_markets

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
            actual_distance = target_price - current_btc
            if YES_PRICE_BUFFER_LOW <= actual_distance <= YES_PRICE_BUFFER_HIGH:
                yes_alert = True
        else:
            actual_distance = current_btc - target_price
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
    print("=== STARTING BOT LOOP DEBUG ===")
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping - no BTC price !!!")
            return
        
        markets = fetch_markets_and_events()
        
        bitcoin_count = 0
        alert_count = 0
        debug_count = 0
        
        for m in markets:
            question = m.get("question", "")
            slug = m.get("slug", "")
            outcomes = m.get("outcomes", [])
            event_title = m.get("event_title", "")
            
            full_text = (question + " " + event_title).lower()
            if "bitcoin" not in full_text and "btc" not in full_text:
                continue
            
            bitcoin_count += 1
            
            if debug_count < 5:
                print("\n========== DEBUG BITCOIN MARKET " + str(debug_count + 1) + " ==========")
                print("Question: " + question)
                if event_title:
                    print("Event: " + event_title)
                print("\nFULL JSON:")
                try:
                    print(json.dumps(m, indent=2))
                except:
                    print(str(m))
                print("=" * 60 + "\n")
                debug_count += 1
            
            direction_keywords = ["above", "over", "below", "under", "hit", "break", "reach", "exceed", "surpass", "pass"]
            has_direction = any(keyword in full_text for keyword in direction_keywords)
            
            if not has_direction:
                print(">>> Bitcoin (no direction): " + question[:60])
                continue
            
            is_above_market = any(word in full_text for word in ["above", "over", "hit", "break", "reach", "exceed", "surpass", "pass"])
            
            yes_prob, no_prob = extract_probabilities(outcomes)
            target_price = extract_target_price(question)
            
            print("\n>>> BITCOIN: " + question[:70])
            print("    YES: " + str(yes_prob) + " | NO: " + str(no_prob))
            print("    Target: $" + str(target_price))
            
            if yes_prob is None or no_prob is None:
                print("    SKIP: No probability")
                continue
            
            if target_price is None:
                print("    SKIP: No target")
                continue
            
            if is_above_market:
                dist = target_price - current_btc_price
            else:
                dist = current_btc_price - target_price
            
            print("    Distance: $" + str(dist))
            print("    In range? " + str(YES_PRICE_BUFFER_LOW <= dist <= YES_PRICE_BUFFER_HIGH))
            
            opportunity = analyze_opportunity(current_btc_price, target_price, yes_prob, no_prob, is_above_market)
            
            if opportunity:
                current_time = time.time()
                if slug in alerted_markets:
                    time_since = current_time - alerted_markets[slug]
                    if time_since < ALERT_COOLDOWN:
                        print("    SKIP: Already alerted")
                        continue
                
                print("    ALERT!")
                alerted_markets[slug] = current_time
                
                rec = opportunity["recommendation"]
                conf = opportunity["confidence"]
                yes_p = opportunity["yes_prob"]
                no_p = opportunity["no_prob"]
                yes_profit = opportunity["yes_profit"]
                no_profit = opportunity["no_profit"]
                distance = opportunity["distance"]
                
                message = "POLYMARKET OPPORTUNITY\n\n"
                message += question + "\n\n"
                message += "Target: $" + str(target_price) + "\n"
                message += "Current BTC: $" + str(int(current_btc_price)) + "\n"
                message += "Distance: $" + str(int(distance)) + "\n\n"
                
                message += "ANALYSIS:\n"
                message += "YES " + str(int(yes_p * 100)) + "% Profit: $" + str(round(yes_profit, 2)) + "\n"
                message += "NO " + str(int(no_p * 100)) + "% Profit: $" + str(round(no_profit, 2)) + "\n\n"
                
                if rec == "YES":
                    message += "BUY YES\n"
                    message += "Confidence: " + conf
                else:
                    message += "BUY NO\n"
                    message += "Confidence: " + conf
                
                message += "\n\nhttps://polymarket.com/market/" + slug
                
                if send_alert(message):
                    alert_count += 1
            else:
                print("    No opportunity")
        
        print("\n=== Bitcoin markets: " + str(bitcoin_count) + ", Alerts: " + str(alert_count) + " ===\n")
        
    except Exception as e:
        print("ERROR: " + str(e))
        import traceback
        traceback.print_exc()

def run_bot():
    print("=== BOT v7 DEBUG MODE ===")
    
    startup_msg = "Bot v7 DEBUG is running\nCheck logs for JSON structure"
    
    if send_alert(startup_msg):
        print("Startup sent")
    
    bot_loop()
    
    print("\nDEBUG RUN COMPLETE - Check logs above")
    
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            bot_loop()
        except Exception as e:
            print("Error: " + str(e))

if __name__ == "__main__":
    from waitress import serve
    
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 8080))
    print("Starting server on port " + str(port))
    serve(app, host="0.0.0.0", port=port)
