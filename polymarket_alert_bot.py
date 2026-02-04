import time
import requests

# ===================== TELEGRAM =====================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ===================== SETTINGS =====================
CHECK_INTERVAL = 15        # seconds
PROBABILITY_THRESHOLD = 0.30   # 30%
ALERT_COOLDOWN = 600       # seconds (10 min)

last_alert_time = {}

# ===================== HELPERS =====================
def send_telegram(message):
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }
    requests.post(TELEGRAM_URL, data=payload, timeout=10)

def get_btc_price():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    data = requests.get(url, timeout=10).json()
    return float(data["price"])

def get_polymarket_markets():
    """
    Fetch Polymarket BTC markets
    """
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "limit": 50,
        "query": "Bitcoin"
    }
    data = requests.get(url, params=params, timeout=15).json()
    return data

# ===================== CORE LOGIC =====================
def check_polymarket():
    btc_price = get_btc_price()
    markets = get_polymarket_markets()

    print(f"BTC Price: {btc_price}")

    for market in markets:
        question = market.get("question", "")
        slug = market.get("slug", "")
        market_url = f"https://polymarket.com/market/{slug}"

        outcomes = market.get("outcomes", [])
        probs = market.get("outcomePrices", [])

        for outcome, prob in zip(outcomes, probs):
            try:
                probability = float(prob)
            except:
                continue

            if probability > PROBABILITY_THRESHOLD:
                continue

            now = time.time()
            key = f"{slug}-{outcome}"

            if key in last_alert_time and now - last_alert_time[key] < ALERT_COOLDOWN:
                continue

            message = (
                f"🚨 *LOW PROBABILITY BTC BET*\n\n"
                f"📊 Market: {question}\n"
                f"🎯 Outcome: {outcome}\n"
                f"📉 Probability: {probability*100:.2f}%\n"
                f"💰 BTC Price: ${btc_price:,.0f}\n\n"
                f"🔗 Bet link:\n{market_url}"
            )

            send_telegram(message)
            last_alert_time[key] = now

# ===================== RUN FOREVER =====================
if __name__ == "__main__":
    print("✅ Polymarket BTC Alert Bot Started")

    while True:
        try:
            check_polymarket()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Error:", e)
            time.sleep(30)

