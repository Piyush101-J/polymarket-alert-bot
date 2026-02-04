import time
import re
import requests
import sys

# ================= TELEGRAM =================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_alert(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ================= SETTINGS =================
CHECK_INTERVAL = 60
MIN_PROB = 0.01
MAX_PROB = 0.40
BUFFER_PERCENT = 0.006

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"

# ================= HELPERS =================
def extract_strike(question):
    m = re.search(r'(\d{2,3},?\d{3})', question)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))

def extract_yes_prob(outcomes):
    if not isinstance(outcomes, list):
        return None

    for o in outcomes:
        if isinstance(o, dict) and o.get("name", "").lower() == "yes":
            try:
                return float(o.get("price"))
            except:
                return None
    return None

def fetch_markets():
    r = requests.get(POLYMARKET_URL, timeout=15)
    r.raise_for_status()
    return r.json()

# ================= BOT LOOP =================
def bot_loop():
    print("✅ Polymarket BTC Alert Bot Running")
    send_alert("✅ Polymarket BTC Alert Bot Running")

    alerted = set()

    while True:
        try:
            markets = fetch_markets()

            for m in markets:
                if not isinstance(m, dict):
                    continue

                question = m.get("question", "")
                slug = m.get("slug", "")
                outcomes = m.get("outcomes")

                if "bitcoin" not in question.lower():
                    continue

                strike = extract_strike(question)
                if not strike:
                    continue

                prob = extract_yes_prob(outcomes)
                if prob is None or not (MIN_PROB <= prob <= MAX_PROB):
                    continue

                key = f"{slug}-{strike}"
                if key in alerted:
                    continue

                buffer = int(strike * BUFFER_PERCENT)
                trigger = strike - buffer

                url = f"https://polymarket.com/market/{slug}"

                msg = (
                    f"📊 Polymarket BTC Alert\n\n"
                    f"🪙 {question}\n"
                    f"🎯 Strike: {strike:,}\n"
                    f"⚠️ Alert Price: {trigger:,}\n"
                    f"📈 YES Probability: {prob*100:.2f}%\n\n"
                    f"🔗 {url}"
                )

                send_alert(msg)
                alerted.add(key)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(30)

# ================= IMMORTAL WRAPPER =================
if __name__ == "__main__":
    while True:
        try:
            bot_loop()
        except Exception as fatal:
            print("Fatal crash:", fatal)
            time.sleep(10)
