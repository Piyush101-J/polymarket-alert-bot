import time
import requests
import re
from threading import Thread
from flask import Flask
import os
from bs4 import BeautifulSoup
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
DISCOVERY_INTERVAL = 3600  # Discover new markets every hour

MIN_YES_PROB = 0.01
MAX_YES_PROB = 0.42
YES_PRICE_BUFFER_LOW = 1500
YES_PRICE_BUFFER_HIGH = 4500

MIN_NO_PROB = 0.70
MAX_NO_PROB = 0.99
NO_PRICE_BUFFER = 5000

MIN_PROFIT_THRESHOLD = 10  # Lowered from 15

ALERT_COOLDOWN = 3600
alerted_markets = {}

# Store discovered URLs
discovered_urls = []
last_discovery_time = 0

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
    
    print("!!! ALL PRICE APIs FAILED !!!")
    return None

def discover_bitcoin_markets():
    """Auto-discover Bitcoin price prediction markets from Polymarket"""
    print("\n=== AUTO-DISCOVERING BITCOIN MARKETS ===")
    
    found_urls = []
    
    try:
        # Search for Bitcoin markets on Polymarket
        search_url = "https://polymarket.com/search?q=bitcoin+above"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"Search page returned {response.status_code}")
            return found_urls
        
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Method 1: Find all links that contain "bitcoin-above"
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Look for event/market URLs with bitcoin-above pattern
            if 'bitcoin-above' in href.lower() and '/event/' in href:
                # Construct full URL
                if href.startswith('/'):
                    full_url = 'https://polymarket.com' + href
                else:
                    full_url = href
                
                # Check if it's a market URL (not just event)
                if full_url.count('/') >= 5:  # event/slug/market-slug format
                    if full_url not in found_urls:
                        found_urls.append(full_url)
                        print(f"  Found: {full_url}")
        
        # Method 2: Try to extract from Next.js data
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        
        if match:
            try:
                data = json.loads(match.group(1))
                
                # Search for market URLs in the data structure
                def find_market_urls(obj, urls_list):
                    if isinstance(obj, dict):
                        # Look for slug or href fields
                        if 'slug' in obj and 'bitcoin-above' in str(obj.get('slug', '')).lower():
                            # Try to construct URL
                            slug = obj['slug']
                            if 'event' in obj:
                                event_slug = obj['event'].get('slug', '')
                                if event_slug:
                                    url = f"https://polymarket.com/event/{event_slug}/{slug}"
                                    if url not in urls_list:
                                        urls_list.append(url)
                        
                        for value in obj.values():
                            find_market_urls(value, urls_list)
                    elif isinstance(obj, list):
                        for item in obj:
                            find_market_urls(item, urls_list)
                
                find_market_urls(data, found_urls)
                
            except Exception as e:
                print(f"  Error parsing Next.js data: {e}")
        
        # Method 3: Try direct crypto category page
        crypto_url = "https://polymarket.com/crypto"
        response = requests.get(crypto_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                if 'bitcoin-above' in href.lower() or 'btc-above' in href.lower():
                    if href.startswith('/'):
                        full_url = 'https://polymarket.com' + href
                    else:
                        full_url = href
                    
                    if full_url.count('/') >= 5:
                        if full_url not in found_urls:
                            found_urls.append(full_url)
                            print(f"  Found (crypto page): {full_url}")
        
        print(f"=== DISCOVERED {len(found_urls)} BITCOIN MARKETS ===\n")
        
    except Exception as e:
        print(f"Error in discovery: {e}")
    
    return found_urls

def extract_target_price_from_url(url):
    """Extract target price from URL like bitcoin-above-66k-on-february-10"""
    match = re.search(r'(\d{2,3})k', url)
    if match:
        return int(match.group(1)) * 1000
    
    match = re.search(r'(\d{5,6})', url)
    if match:
        return int(match.group(1))
    
    return None

def scrape_polymarket_page(url):
    """Scrape a Polymarket page to get probabilities"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"    Page returned status {response.status_code}")
            return None
        
        html = response.text
        
        # Try to find JSON data in the page
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        
        if match:
            try:
                data = json.loads(match.group(1))
                
                # Search recursively for outcomePrices
                def find_outcome_prices(obj):
                    if isinstance(obj, dict):
                        if 'outcomePrices' in obj:
                            return obj
                        for value in obj.values():
                            result = find_outcome_prices(value)
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for item in obj:
                            result = find_outcome_prices(item)
                            if result:
                                return result
                    return None
                
                market_data = find_outcome_prices(data)
                if market_data:
                    outcomes = market_data.get('outcomePrices', [])
                    if isinstance(outcomes, str):
                        outcomes = json.loads(outcomes)
                    
                    if len(outcomes) >= 2:
                        yes_prob = float(outcomes[0])
                        no_prob = float(outcomes[1])
                        
                        return {
                            'yes_prob': yes_prob,
                            'no_prob': no_prob,
                            'question': market_data.get('question', ''),
                            'closed': market_data.get('closed', False)
                        }
                    
            except Exception as e:
                print(f"    Error parsing JSON: {e}")
        
        # Fallback: scrape visible percentages
        soup = BeautifulSoup(html, 'html.parser')
        
        percentages = []
        for text in soup.stripped_strings:
            match = re.search(r'(\d{1,2})%', text)
            if match:
                percentages.append(int(match.group(1)))
        
        if len(percentages) >= 2:
            yes_prob = percentages[0] / 100.0
            no_prob = percentages[1] / 100.0
            
            return {
                'yes_prob': yes_prob,
                'no_prob': no_prob,
                'question': 'Scraped from HTML',
                'closed': False
            }
        
        return None
        
    except Exception as e:
        print(f"    Error scraping: {e}")
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
    global discovered_urls, last_discovery_time
    
    print("=== STARTING BOT LOOP ===")
    
    # Auto-discover markets every hour
    current_time = time.time()
    if current_time - last_discovery_time > DISCOVERY_INTERVAL:
        print("Time for market discovery!")
        new_urls = discover_bitcoin_markets()
        
        if new_urls:
            discovered_urls = new_urls
            last_discovery_time = current_time
            print(f"Updated market list: {len(discovered_urls)} markets")
        else:
            print("No new markets found, keeping existing list")
    
    if not discovered_urls:
        print("!!! No markets to monitor - will try discovery next cycle !!!")
        return
    
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping - no BTC price !!!")
            return
        
        print(f"\n=== CHECKING {len(discovered_urls)} MARKETS ===\n")
        
        alert_count = 0
        success_count = 0
        failed_count = 0
        
        for url in discovered_urls:
            print(f">>> Scraping: {url.split('/')[-1]}")
            
            target_price = extract_target_price_from_url(url)
            
            if not target_price:
                print(f"    SKIP: No target price in URL")
                failed_count += 1
                continue
            
            print(f"    Target: ${target_price:,}")
            
            market_data = scrape_polymarket_page(url)
            
            if not market_data:
                print(f"    SKIP: Could not scrape")
                failed_count += 1
                continue
            
            if market_data.get('closed', False):
                print(f"    SKIP: Market closed")
                failed_count += 1
                continue
            
            success_count += 1
            
            yes_prob = market_data['yes_prob']
            no_prob = market_data['no_prob']
            
            print(f"    ✅ YES: {yes_prob:.2%} | NO: {no_prob:.2%}")
            
            dist = target_price - current_btc_price
            
            print(f"    Distance: ${dist:,}")
            print(f"    In range? {YES_PRICE_BUFFER_LOW <= dist <= YES_PRICE_BUFFER_HIGH}")
            print(f"    Prob in range? {MIN_YES_PROB <= yes_prob <= MAX_YES_PROB}")
            
            opportunity = analyze_opportunity(current_btc_price, target_price, yes_prob, no_prob)
            
            if opportunity:
                url_id = url.split('/')[-1]
                current_time_check = time.time()
                
                if url_id in alerted_markets:
                    time_since = current_time_check - alerted_markets[url_id]
                    if time_since < ALERT_COOLDOWN:
                        print(f"    SKIP: Already alerted {int(time_since/60)} min ago")
                        continue
                
                print("    *** SENDING ALERT! ***")
                alerted_markets[url_id] = current_time_check
                
                rec = opportunity["recommendation"]
                conf = opportunity["confidence"]
                yes_p = opportunity["yes_prob"]
                no_p = opportunity["no_prob"]
                yes_profit = opportunity["yes_profit"]
                no_profit = opportunity["no_profit"]
                distance = opportunity["distance"]
                
                message = "🎯 POLYMARKET OPPORTUNITY!\n\n"
                message += f"📊 Bitcoin above ${target_price:,}\n\n"
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
                
                message += f"\n\n🔗 {url}"
                
                if send_alert(message):
                    alert_count += 1
                    print("    ✅ ALERT SENT!")
            else:
                print("    No opportunity")
        
        print(f"\n=== SUMMARY ===")
        print(f"Markets Monitored: {len(discovered_urls)}")
        print(f"Successfully Scraped: {success_count} ✅")
        print(f"Failed: {failed_count} ❌")
        print(f"Alerts Sent: {alert_count} 🔔")
        print(f"===============\n")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def run_bot():
    global last_discovery_time
    
    print("=== BOT v17 ULTIMATE - AUTO-DISCOVERY ===")
    
    # Do initial discovery
    print("Performing initial market discovery...")
    discovered_urls_initial = discover_bitcoin_markets()
    
    if discovered_urls_initial:
        global discovered_urls
        discovered_urls = discovered_urls_initial
        last_discovery_time = time.time()
    
    startup_msg = "🎯 Bot v17 ULTIMATE is LIVE!\n\n"
    startup_msg += "✅ AUTO-DISCOVERS Bitcoin markets\n"
    startup_msg += "✅ No manual URL updates needed!\n"
    startup_msg += "✅ Rediscovers markets every hour\n"
    startup_msg += f"✅ Found {len(discovered_urls)} markets initially\n\n"
    startup_msg += "Fully automated!"
    
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
