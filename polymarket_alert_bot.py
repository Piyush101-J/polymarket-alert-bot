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
CHECK_INTERVAL = 60          # seconds
MIN_PROB = 0.01              # 1%
MAX_PROB = 0.40              # 40%

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

# ================= HELPERS =================
def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

def extract_yes_probability(outcomes):
    if not isinstance(outcomes, list):
        return None

    for o in outcomes:
        if isinstance(o, dict) and o.get("name", "").lower() == "yes":
            try:
                return float(o.get("price"))
            except:
                return None
    return None

def extract_price_from_question(question):
    # Example: "Bitcoin above 80000 on February 4?"
    nums = [int(s.replace(",", "")) for s in question.split() if s.replace(",", "").isdigit()]
    return max(nums) if nums else None

# ================= CORE LOOP =================
def bot_loop():
    markets = fetch_markets()

    for m in markets:
        if not isinstance(m, dict):
            continue

        question = m.get("question", "")
        slug = m.get("slug", "")
        outcomes = m.get("outcomes")

        if "bitcoin above" not in question.lower():
            continue

        prob = extract_yes_probability(outcomes)
        target_price = extract_price_from_question(question)

        if prob is None or target_price is None:
            continue

        if MIN_PROB <= prob <= MAX_PROB:
            url = f"https://polymarket.com/market/{slug}"

            message = (
                f"🚨 *EARLY POLYMARKET ALERT*\n\n"
                f"🪙 {question}\n"
                f"🎯 Target Price: {target_price:,}\n"
                f"📊 YES Probability: {prob*100:.2f}%\n\n"
                f"🔗 {url}"
            )
            send_alert(message)

# ================= BOOTSTRAP =================
if __name__ == "__main__":
    print("🚀 Worker booted, running permanently")
    send_alert("🚀 Polymarket BTC Alert Bot is LIVE")

    while True:
        try:
            bot_loop()
        except Exception as e:
            print("Error:", e)
        time.sleep(CHECK_INTERVAL)

