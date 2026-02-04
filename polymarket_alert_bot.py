import requests
import time

# ================= TELEGRAM =================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

def send_alert(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": False
    }
    requests.post(url, data=payload, timeout=10)

# ================= SETTINGS =================
POLYMARKET_API = "https://gamma-api.polymarket.com/markets"

MIN_PROB = 0.30   # 30%
MAX_PROB = 0.40   # 40%

CHECK_INTERVAL = 60      # seconds
ALERT_COOLDOWN = 900    # 15 minutes

last_alert = {}

# ================= CORE LOGIC =================
def fetch_markets():
    r = requests.get(POLYMARKET_API, timeout=10)
    return r.json()

def check_markets():
    markets = fetch_markets()

    for m in markets:
        title = m.get("question", "").lower()

        # Only BTC "above" markets
        if "bitcoin" not in title or "above" not in title:
            continue

        outcomes = m.get("outcomes", [])
        prices = m.get("outcomePrices", [])

        if "Yes" not in outcomes:
            continue

        yes_index = outcomes.index("Yes")
        prob = float(prices[yes_index])  # YES price = probability

        if MIN_PROB <= prob <= MAX_PROB:
            market_id = m["id"]
            market_url = f"https://polymarket.com/market/{market_id}"
            now = time.time()

            if market_id not in last_alert or now - last_alert[market_id] > ALERT_COOLDOWN:
                msg = (
                    f"📊 POLYMARKET BTC ALERT\n\n"
                    f"🪙 {m['question']}\n"
                    f"🎯 Probability: {prob*100:.1f}%\n"
                    f"💰 YES price: {prob*100:.1f}¢\n\n"
                    f"🔗 Open market:\n{market_url}\n\n"
                    f"✅ Probability in 30–40% range"
                )

                send_alert(msg)
                last_alert[market_id] = now

# ================= LOOP =================
if __name__ == "__main__":
    send_alert("🚀 Polymarket BTC Alert Bot Started")
    while True:
        try:
            check_markets()
        except Exception as e:
            send_alert(f"⚠️ Error: {e}")
        time.sleep(CHECK_INTERVAL)
