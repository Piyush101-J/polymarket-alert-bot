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
DISCOVERY_INTERVAL = 3600  # Auto-discover every hour

MIN_YES_PROB = 0.01
MAX_YES_PROB = 0.42
YES_PRICE_BUFFER_LOW = 1500
YES_PRICE_BUFFER_HIGH = 4500

MIN_NO_PROB = 0.70
MAX_NO_PROB = 0.99
NO_PRICE_BUFFER = 5000

MIN_PROFIT_THRESHOLD = 10

ALERT_COOLDOWN = 3600
alerted_markets = {}

# ============================================
# MANUAL SEED URLS - ADD YOUR MARKETS HERE!
# ============================================
MANUAL_SEED_URLS = [
   
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-68k-on-february-8",
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-70k-on-february-8",
    
    "https://polymarket.com/event/bitcoin-above-on-february-7/bitcoin-above-70k-on-february-7",
    "https://polymarket.com/event/bitcoin-above-on-february-7/bitcoin-above-70k-on-february-7",
    "https://polymarket.com/event/bitcoin-above-on-february-7/bitcoin-above-72k-on-february-7",
    "https://polymarket.com/event/bitcoin-above-on-february-7/bitcoin-above-74k-on-february-7",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-66k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-68k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-70k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-72k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-10/bitcoin-above-74k-on-february-10",
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-72k-on-february-8",
    "https://polymarket.com/event/bitcoin-above-on-february-8/bitcoin-above-74k-on-february-8",
    "https://polymarket.com/event/bitcoin-above-on-february-9/bitcoin-above-68k-on-february-9",
    "https://polymarket.com/event/bitcoin-above-on-february-9/bitcoin-above-70k-on-february-9",
    "https://polymarket.com/event/bitcoin-above-on-february-9/bitcoin-above-72k-on-february-9",
    "https://polymarket.com/event/bitcoin-above-on-february-9/bitcoin-above-74k-on-february-9",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-64k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-66k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-68k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-70k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-72k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-11/bitcoin-above-74k-on-february-11",
    "https://polymarket.com/event/bitcoin-above-on-february-12/bitcoin-above-66k-on-february-12",
    "https://polymarket.com/event/bitcoin-above-on-february-12/bitcoin-above-68k-on-february-12",
    "https://polymarket.com/event/bitcoin-above-on-february-12/bitcoin-above-70k-on-february-12",
    "https://polymarket.com/event/bitcoin-above-on-february-12/bitcoin-above-72k-on-february-12",
    "https://polymarket.com/event/bitcoin-above-on-february-12/bitcoin-above-74k-on-february-12",
    
    # Add more URLs here as you find them!
]

# Store auto-discovered URLs
auto_discovered_urls = []
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
    """Auto-discover Bitcoin markets from Polymarket"""
    print("\n=== AUTO-DISCOVERING BITCOIN MARKETS ===")
    
    found_urls = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Method 1: Search page
        search_queries = ["bitcoin+above", "btc+above"]
        
        for search_query in search_queries:
            search_url = f"https://polymarket.com/search?q={search_query}"
            
            try:
                response = requests.get(search_url, headers=headers, timeout=15)
                
                if response.status_code != 200:
                    print(f"  Search '{search_query}' returned {response.status_code}")
                    continue
                
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find all links
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    if ('bitcoin-above' in href.lower() or 'btc-above' in href.lower()) and '/event/' in href:
                        if href.startswith('/'):
                            full_url = 'https://polymarket.com' + href
                        else:
                            full_url = href
                        
                        # Must be market URL (has both event and market slug)
                        if full_url.count('/') >= 5:
                            if full_url not in found_urls:
                                found_urls.append(full_url)
                                print(f"  Found: {full_url.split('/')[-1]}")
            except Exception as e:
                print(f"  Error searching '{search_query}': {e}")
        
        # Method 2: Crypto category page
        try:
            crypto_url = "https://polymarket.com/crypto"
            response = requests.get(crypto_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    if ('bitcoin-above' in href.lower() or 'btc-above' in href.lower()):
                        if href.startswith('/'):
                            full_url = 'https://polymarket.com' + href
                        else:
                            full_url = href
                        
                        if full_url.count('/') >= 5:
                            if full_url not in found_urls:
                                found_urls.append(full_url)
                                print(f"  Found (crypto): {full_url.split('/')[-1]}")
        except Exception as e:
            print(f"  Error checking crypto page: {e}")
        
        print(f"=== AUTO-DISCOVERED {len(found_urls)} MARKETS ===\n")
        
    except Exception as e:
        print(f"Error in discovery: {e}")
    
    return found_urls

def extract_target_price_from_url(url):
    """Extract target price from URL"""
    match = re.search(r'(\d{2,3})k', url)
    if match:
        return int(match.group(1)) * 1000
    
    match = re.search(r'(\d{5,6})', url)
    if match:
        return int(match.group(1))
    
    return None

def scrape_polymarket_page(url):
    """Scrape Polymarket page to get probabilities"""
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
    global auto_discovered_urls, last_discovery_time
    
    print("=== STARTING BOT LOOP ===")
    
    # Auto-discover markets every hour
    current_time = time.time()
    
    if current_time - last_discovery_time > DISCOVERY_INTERVAL:
        print("🔍 Time for auto-discovery!")
        newly_discovered = discover_bitcoin_markets()
        
        if newly_discovered:
            auto_discovered_urls = newly_discovered
            last_discovery_time = current_time
        else:
            print("No new markets found via auto-discovery")
    
    # COMBINE manual + auto-discovered URLs (remove duplicates)
    all_urls = list(set(MANUAL_SEED_URLS + auto_discovered_urls))
    
    if not all_urls:
        print("!!! No markets to monitor !!!")
        return
    
    print(f"\n=== MONITORING {len(all_urls)} TOTAL MARKETS ===")
    print(f"  📝 Manual seed URLs: {len(MANUAL_SEED_URLS)}")
    print(f"  🔍 Auto-discovered: {len(auto_discovered_urls)}")
    print(f"  📊 Total (deduplicated): {len(all_urls)}\n")
    
    try:
        current_btc_price = get_current_btc_price()
        
        if current_btc_price is None:
            print("!!! Skipping - no BTC price !!!")
            return
        
        alert_count = 0
        success_count = 0
        failed_count = 0
        
        for url in all_urls:
            market_name = url.split('/')[-1]
            print(f">>> Scraping: {market_name}")
            
            target_price = extract_target_price_from_url(url)
            
            if not target_price:
                print(f"    SKIP: No target price in URL")
                failed_count += 1
                continue
            
            print(f"    Target: ${target_price:,}")
            
            market_data = scrape_polymarket_page(url)
            
            if not market_data:
                print(f"    SKIP: Could not scrape page")
                failed_count += 1
                continue
            
            if market_data.get('closed', False):
                print(f"    SKIP: Market closed ⏰")
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
                url_id = market_name
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
                    print("    ✅ ALERT SENT TO TELEGRAM!")
            else:
                print("    No opportunity (outside criteria)")
        
        print(f"\n=== SUMMARY ===")
        print(f"Total Markets: {len(all_urls)}")
        print(f"Successfully Scraped: {success_count} ✅")
        print(f"Failed to Scrape: {failed_count} ❌")
        print(f"Alerts Sent: {alert_count} 🔔")
        print(f"===============\n")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def run_bot():
    global last_discovery_time, auto_discovered_urls
    
    print("=== BOT v17.5 HYBRID - MANUAL + AUTO ===")
    print(f"📝 Manual seed URLs: {len(MANUAL_SEED_URLS)}")
    
    # Do initial discovery
    print("\n🔍 Performing initial auto-discovery...")
    initial_discovery = discover_bitcoin_markets()
    
    if initial_discovery:
        auto_discovered_urls = initial_discovery
        last_discovery_time = time.time()
        print(f"✅ Found {len(initial_discovery)} markets via auto-discovery")
    else:
        print("⚠️ Auto-discovery found 0 markets (will rely on manual URLs)")
    
    total_initial = len(set(MANUAL_SEED_URLS + auto_discovered_urls))
    
    startup_msg = "🎯 Bot v17.5 HYBRID is LIVE!\n\n"
    startup_msg += f"✅ Manual URLs: {len(MANUAL_SEED_URLS)}\n"
    startup_msg += f"✅ Auto-discovered: {len(auto_discovered_urls)}\n"
    startup_msg += f"✅ Total monitoring: {total_initial}\n\n"
    startup_msg += "📝 Manual URLs = guaranteed tracking\n"
    startup_msg += "🔍 Auto-discovery = bonus coverage\n\n"
    startup_msg += "Best of both worlds!"
    
    if send_alert(startup_msg):
        print("✅ Startup message sent to Telegram!")
    
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
