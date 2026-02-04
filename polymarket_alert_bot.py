import time
import re
import requests

# ================= TELEGRAM =================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

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
BUFFER_PERCENT = 0.006     # 0.6% auto buffer

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

# ================= HELPERS =================
def extract_strike_from_question(question):
    """
    Extracts strike price like 80000 from:
    'Bitcoin above 80,000 on February 4?'
    """
    m = re.search(r'(\d{2,3},?\d{3})', question)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))

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

def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

# ================= CORE =================
def run():
    print("✅ Polymarket BTC Alert Bot Started")
    send_alert("✅ Polymarket BTC Alert Bot Started")

    alerted = set()  # prevent spam for same market

    while True:
        try:
            markets = fetch_markets()

            for m in markets:
                if not isinstance(m, dict):
                    continue

                question = m.get("question", "")
                slug = m.get("slug", "")
                outcomes = m.get("outcomes")

                if not question or not slug:
                    continue

                # Focus only on Bitcoin markets
                if "bitcoin" not in question.lower():
                    continue

                strike = extract_strike_from_question(question)
                if not strike:
                    continue

                prob = extract_yes_probability(outcomes)
                if prob is None:
                    continue

                if not (MIN_PROB <= prob <= MAX_PROB):
                    continue

                buffer = int(strike * BUFFER_PERCENT)
                trigger_price = strike - buffer

                market_id = f"{slug}-{strike}"
                if market_id in alerted:
                    continue

                url = f"https://polymarket.com/market/{slug}"

                message = (
                    f"📊 *Polymarket BTC Alert*\n\n"
                    f"🪙 {question}\n"
                    f"🎯 Strike: {strike:,}\n"
                    f"⚠️ Alert Trigger: {trigger_price:,}\n"
                    f"📈 YES Probability: {prob*100:.2f}%\n\n"
                    f"🔗 {url}"
                )

                send_alert(message)
                alerted.add(market_id)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(30)

# ================= START =================
if __name__ == "__main__":
    run()

