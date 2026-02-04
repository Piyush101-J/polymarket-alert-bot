import websocket
import json
import time
import threading
import requests
from bs4 import BeautifulSoup

# ================== TELEGRAM ==================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"
CHAT_ID = "1771346124"

# ================== CONSERVATIVE STRIKES ==================
STRIKES = {
    70000: {"buffer": 700, "max_prob": 0.48},
    72000: {"buffer": 600, "max_prob": 0.46},
    74000: {"buffer": 500, "max_prob": 0.44},
}

PROB_CHECK_INTERVAL = 10      # seconds
ALERT_COOLDOWN = 600          # 10 minutes

btc_price = None
last_alert_time = {}

# ================== TELEGRAM SEND ==================
def send_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload, timeout=5)

# ================== BTC REAL-TIME ==================
def on_message(ws, message):
    global btc_price
    data = json.loads(message)
    btc_price = float(data["p"])

def start_btc_ws():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=on_message
    )
    ws.run_forever()

# ================== POLYMARKET PROBABILITY ==================
def get_probability():
    try:
        html = requests.get("https://polymarket.com", timeout=5).text
        soup = BeautifulSoup(html, "html.parser")

        for text in soup.stripped_strings:
            if "%" in text:
                try:
                    p = float(text.replace("%", "")) / 100
                    if 0 < p < 1:
                        return p
                except:
                    pass
    except:
        pass
    return None

# ================== MONITOR LOGIC ==================
def monitor():
    while True:
        if btc_price is None:
            time.sleep(1)
            continue

        prob = get_probability()
        if prob is None:
            time.sleep(PROB_CHECK_INTERVAL)
            continue

        now = time.time()

        for strike, cfg in STRIKES.items():
            near_strike = btc_price >= (strike - cfg["buffer"])
            prob_ok = prob <= cfg["max_prob"]
            last = last_alert_time.get(strike, 0)

            if near_strike and prob_ok and (now - last > ALERT_COOLDOWN):
                send_alert(
                    f"🚨 CONSERVATIVE ENTRY ALERT\n\n"
                    f"BTC Price: ${btc_price:,.0f}\n"
                    f"Strike: {strike}\n"
                    f"YES Probability: {prob*100:.1f}%\n\n"
                    f"Polymarket lag detected.\n"
                    f"Manual check recommended."
                )
                last_alert_time[strike] = now

        time.sleep(PROB_CHECK_INTERVAL)

# ================== START BOT ==================
threading.Thread(target=start_btc_ws, daemon=True).start()
monitor()
