import time
import requests

BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

API_URL = "https://gamma-api.polymarket.com/markets"

CHECK_INTERVAL = 30
MIN_PROB = 0.01   # 1%
MAX_PROB = 0.40   # 40%

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "disable_web_page_preview": False
    }
    requests.post(url, json=payload, timeout=10)

print("✅ Polymarket BTC Alert Bot Started")

while True:
    try:
        res = requests.get(API_URL, timeout=15)
        markets = res.json()

        for market in markets:
            title = market.get("question", "")
            slug = market.get("slug", "")
            outcomes = market.get("outcomes", [])

            if "bitcoin" not in title.lower():
                continue

            for o in outcomes:
                name = o.get("name")
                yes_price = o.get("yesPrice")

                if yes_price is None:
                    continue

                prob = float(yes_price)

                if MIN_PROB <= prob <= MAX_PROB:
                    link = f"https://polymarket.com/market/{slug}"

                    msg = (
                        f"📊 Polymarket BTC Alert\n\n"
                        f"🪙 Market: {title}\n"
                        f"🎯 Strike: {name}\n"
                        f"📈 Probability: {prob*100:.2f}%\n\n"
                        f"🔗 {link}"
                    )

                    send_telegram(msg)

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(10)
