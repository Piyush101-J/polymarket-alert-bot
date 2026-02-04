import time
import requests

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
    requests.post(url, json=payload, timeout=10)

# ================= SETTINGS =================
CHECK_INTERVAL = 60        # seconds
MIN_PROB = 0.01            # 1%
MAX_PROB = 0.40            # 40%

# Polymarket API (official public endpoint)
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

# ================= CORE LOGIC =================
def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

def extract_yes_probability(outcomes):
    """
    Safely extract YES probability
    """
    if not isinstance(outcomes, list):
        return None

    for o in outcomes:
        if not isinstance(o, dict):
            continue
        if o.get("name", "").lower() == "yes":
            price = o.get("price")
            if price is None:
                return None
            try:
                return float(price)
            except:
                return None
    return None

def run():
    print("✅ Polymarket BTC Alert Bot Started")
    send_alert("✅ Polymarket BTC Alert Bot Started")

    while True:
        try:
            markets = fetch_markets()

            for m in markets:
                if not isinstance(m, dict):
                    continue

                question = m.get("question", "")
                slug = m.get("slug", "")
                url = f"https://polymarket.com/market/{slug}"

                # Focus only on Bitcoin markets
                if "bitcoin" not in question.lower():
                    continue

                outcomes = m.get("outcomes")
                prob = extract_yes_probability(outcomes)

                if prob is None:
                    continue

                if MIN_PROB <= prob <= MAX_PROB:
                    message = (
                        f"📊 *Polymarket Alert*\n\n"
                        f"🪙 {question}\n"
                        f"📈 YES Probability: {prob*100:.2f}%\n"
                        f"🔗 {url}"
                    )
                    send_alert(message)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(30)

# ================= START =================
if __name__ == "__main__":
    run()

