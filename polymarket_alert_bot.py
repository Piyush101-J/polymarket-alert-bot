import time
import requests
import re
from threading import Thread
from flask import Flask
import os
from datetime import datetime, timezone

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

# SECURE: Credentials from environment variables only
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

# YOUR OPTIMIZED SETTINGS
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
    # Look for price patterns like 70000, 70,000, 70k, $70k, etc.
    patterns = [
        r'\$?(\d{1,3}),?(\d{3})',  # 70,000 or $70,000
        r'(\d{5,6})',               # 70000
        r'(\d{2,3})k',              # 70k
        r'\$(\d{2,3})k'             # $70k
    ]
    
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            if 'k' in question.lower():
                # Handle "70k" format
                num = match.group(1)
                return int(num) * 1000
            elif ',' in match.group(0):
                # Handle "70,000" format
                return int(match.group(1) + match.group(2))
            else:
                # Handle "70000" format
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
    
    return yes_prob, no_prob

def is_market_expired(market):
    """Check if market is expired or closed"""
    try:
        # Check closed flag
        if market.get("closed", False):
            return True
        
        # Check end date
        end_date = market.get("end_date_iso") or market.get("endDate") or market.get("end_date")
        if not end_date:
            return False  # No end date, assume active
        
        current_time = datetime.now(timezone.utc)
        
        # Parse end date
        if isinstance(end_date, str):
            # Remove timezone indicator and parse
            end_date_clean = end_date.replace('Z', '+00:00')
            try:
                end_dt = datetime.fromisoformat(end_date_clean)
            except:
                # Try parsing as timestamp
                try:
                    end_dt = datetime.fromtimestamp(float(end_date), tz=timezone.utc)
                except:
                    return False
        elif isinstance(end_date, (int, float)):
            end_dt = datetime.fromtimestamp(end_date, tz=timezone.utc)
        else:
            return False
        
        # Market is expired if end date is in the past
        return end_dt < current_time
    except Exception as e:
        print("Error checking expiration: " + str(e))
        return False

def fetch_markets():
    """Fetch CURRENT active markets, filter out expired ones"""
    all_markets = []
    seen_slugs = set()
    
    print("=== FETCHING CURRENT MARKETS ===")
    
    # Strategy: Get markets sorted by volume (most active = most recent)
    try:
        print("Fetching high-volume markets...")
        url = "https://gamma-api.polymarket.com/markets?limit=200&closed=false"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        markets = response.json()
        
        print("Received " + str(len(markets)) + " markets, filtering...")
        
        expired_count = 0
        for m in markets:
            slug = m.get("slug", "")
            if not slug or slug in seen_slugs:
                continue
            
            # Filter out expired markets
            if is_market_expired(m):
                expired_count += 1
                continue
            
            all_markets.append(m)
            seen_slugs.add(slug)
        
        print("Kept " + str(len(all_markets)) + " active markets, filtered out " + str(expired_count) + " expired")
    except Exception as e:
        print("Error fetching markets: " + str(e))
    
    print("=== TOTAL CURRENT MARKETS: " + str(len(all_markets)) + " ===")
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
    print("=== STARTING BOT LOOP ===")
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping this check - couldn't fetch BTC price !!!")
            return
        
        markets = fetch_markets()
        
        # Show first 20 markets for debugging
        print("\n=== SAMPLE MARKETS (First 20) ===")
        for i, m in enumerate(markets[:20], 1):
            question = m.get("question", "Unknown")
            print(str(i) + ". " + question[:70])
        print("=== END SAMPLE ===\n")
        
        bitcoin_count = 0
        alert_count = 0
        
        for m in markets:
            question = m.get("question", "")
            slug = m.get("slug", "")
            outcomes = m.get("outcomes", [])
            
            # Check for Bitcoin/BTC
            if "bitcoin" not in question.lower() and "btc" not in question.lower():
                continue
            
            bitcoin_count += 1
            print("\n>>> FOUND Bitcoin market: " + question)
            
            # Check for directional keywords (expanded list!)
            direction_keywords = ["above", "over", "below", "under", "hit", "break", "reach", "exceed", "surpass", "pass"]
            has_direction = any(keyword in question.lower() for keyword in direction_keywords)
            
            if not has_direction:
                print("    SKIP: No directional keyword")
                continue
            
            # Assume bullish/above for most Bitcoin bets
            is_above_market = any(word in question.lower() for word in ["above", "over", "hit", "break", "reach", "exceed", "surpass", "pass"])
            if not is_above_market:
                is_above_market = "below" not in question.lower() and "under" not in question.lower()
            
            yes_prob, no_prob = extract_probabilities(outcomes)
            target_price = extract_target_price(question)
            
            print("    YES prob: " + str(yes_prob) + " | NO prob: " + str(no_prob))
            print("    Target price: $" + str(target_price))
            print("    Current BTC: $" + str(current_btc_price))
            
            if yes_prob is None or no_prob is None:
                print("    SKIP: Missing probability data")
                continue
            
            if target_price is None:
                print("    SKIP: Could not extract target price")
                continue
            
            # Calculate distance
            if is_above_market:
                dist = target_price - current_btc_price
            else:
                dist = current_btc_price - target_price
            
            print("    Distance: $" + str(dist))
            print("    In range ($1,500-$4,500)? " + str(YES_PRICE_BUFFER_LOW <= dist <= YES_PRICE_BUFFER_HIGH))
            print("    Probability in range (1%-42%)? " + str(MIN_YES_PROB <= yes_prob <= MAX_YES_PROB))
            
            opportunity = analyze_opportunity(current_btc_price, target_price, yes_prob, no_prob, is_above_market)
            
            if opportunity:
                current_time = time.time()
                if slug in alerted_markets:
                    time_since_alert = current_time - alerted_markets[slug]
                    if time_since_alert < ALERT_COOLDOWN:
                        print("    SKIP: Already alerted " + str(int(time_since_alert/60)) + " min ago")
                        continue
                
                print("    ✅ OPPORTUNITY FOUND! SENDING ALERT!")
                alerted_markets[slug] = current_time
                
                rec = opportunity["recommendation"]
                conf = opportunity["confidence"]
                yes_p = opportunity["yes_prob"]
                no_p = opportunity["no_prob"]
                yes_profit = opportunity["yes_profit"]
                no_profit = opportunity["no_profit"]
                distance = opportunity["distance"]
                
                message = "🎯 POLYMARKET ALERT!\n\n"
                message += "📊 " + question + "\n\n"
                message += "🎯 Target: $" + str(target_price) + "\n"
                message += "💰 Current BTC: $" + str(int(current_btc_price)) + "\n"
                message += "📏 Distance: $" + str(int(distance)) + "\n\n"
                
                message += "ANALYSIS:\n"
                message += "├─ YES @ " + str(int(yes_p * 100)) + "% → Profit: +$" + str(round(yes_profit, 2)) + "\n"
                message += "└─ NO @ " + str(int(no_p * 100)) + "% → Profit: +$" + str(round(no_profit, 2)) + "\n\n"
                
                if rec == "YES":
                    message += "🧠 RECOMMENDATION: BUY YES ✅\n"
                    message += "📈 Confidence: " + conf + "\n"
                    message += "💡 BTC is $" + str(int(distance)) + " from target"
                else:
                    message += "🧠 RECOMMENDATION: BUY NO ✅\n"
                    message += "📈 Confidence: " + conf + "\n"
                    message += "💡 Very unlikely to reach target"
                
                message += "\n\n🔗 https://polymarket.com/market/" + slug
                
                if send_alert(message):
                    alert_count += 1
                    print("    ✅ ALERT SENT TO TELEGRAM!")
                else:
                    print("    ❌ Failed to send alert")
            else:
                print("    ❌ No opportunity (filters not matched)")
        
        print("\n=== Check complete. Bitcoin markets: " + str(bitcoin_count) + ", Alerts sent: " + str(alert_count) + " ===\n")
        
    except Exception as e:
        print("!!! ERROR in bot_loop: " + str(e))
        import traceback
        traceback.print_exc()

def run_bot():
    print("=== POLYMARKET BOT v5 ULTIMATE - STARTING ===")
    
    startup_msg = "🚀 Polymarket Bot v5 ULTIMATE is LIVE!\n\n"
    startup_msg += "✅ Settings optimized for CURRENT markets\n"
    startup_msg += "✅ Filters out expired 2020-2021 markets\n"
    startup_msg += "✅ Fetches 200 high-volume markets\n"
    startup_msg += "✅ YES: 1%-42% probability\n"
    startup_msg += "✅ Distance: $1,500-$4,500\n"
    startup_msg += "✅ Keywords: above/hit/break/reach/exceed\n\n"
    startup_msg += "💪 Ready to catch those opportunities!"
    
    if send_alert(startup_msg):
        print("✅ Startup message sent!")
    else:
        print("❌ Failed to send startup message")
    
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
