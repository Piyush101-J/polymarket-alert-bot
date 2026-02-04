import time
import requests

# ================== TELEGRAM ==================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

def send_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }
    requests.post(url, json=payload, timeout=10)

# ================== SETTINGS ==================
CHECK_INTERVAL = 30  # seconds
ALERT_COOLDOWN = 600  # 10 minutes
MIN_PROB = 0.01   # 1%
MAX_PROB = 0.40   # 40%

# Polymarket API (Bitcoin markets)
POLYMARKET_API = "https://gamma-api.polymarket.com/markets"

# Keywords to filter correct bets
KEYWORDS = [
    "Bitcoin above",
    "What price will Bitcoin hit",
    "Bitcoin hit February"
]

last_alert_time = {}

print("✅ Polymarket BTC Alert Bot Started")

# ================== MAIN LOOP ==================
while True:
    try:
        response = requests.get(POLYMARKET_API, timeout=10)
        markets = response.json()

        for market in markets:
            title = market.get("question", "")
            slug = market.get("slug", "")
            outcomes = market.get("outcomes", [])

            # Filter only BTC-related markets
            if not any(k.lower() in title.lower() for k in KEYWORDS):
                continue

            for outcome in outcomes:
                name = outcome.get("name", "")
                yes_price = outcome.get("yesPrice")

                if yes_price is None:
                    continue

                prob = float(yes_price)

                if MIN_PROB <= prob <= MAX_PROB:
                    now = time.time()
                    key = f"{slug}-{name}"

                    if key in last_alert_time and now - last_alert_time[key] < ALERT_COOLDOWN:
                        continue

                    market_url = f"https://polymarket.com/market/{slug}"

                    message = (
                        f"📊 *Polymarket BTC Alert*\n\n"
                        f"🪙 Market: {title}\n"
                        f"🎯 Option: {name}\n"
                        f"📈 Probability: {prob*100:.2f}%\n\n"
                        f"🔗 {market_url}"
                    )

                    send_alert(message)
                    last_alert_time[key] = now

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
