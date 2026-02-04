import requests
from flask import Flask
import os

app = Flask(__name__)

# ================= TELEGRAM =================
BOT_TOKEN = "8534636585: AAHGUIe4wVSiR×1z0_UDqIU1l_xIija4-wo"  # Replace with actual token
CHAT_ID = "1771346124"              # Replace with actual chat ID

@app.route('/')
def health():
    return "Bot is running", 200

@app.route('/test')
def test_telegram():
    """Test endpoint to send a message"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": "🧪 TEST MESSAGE - If you see this, Telegram works!"
        }
        response = requests.post(url, json=payload, timeout=10)
        return f"Response: {response.status_code} - {response.text}", 200
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting test server on port {port}")
    print(f"Visit: https://your-railway-url.up.railway.app/test")
    app.run(host="0.0.0.0", port=port)
```

**Deploy this and visit:** `https://your-railway-url.up.railway.app/test`

You should see either:
- ✅ "Response: 200" (success)
- ❌ An error message

---

## Step 2: Get Your Correct CHAT_ID

If the test fails, your `CHAT_ID` might be wrong. Here's how to get it:

**Method 1: Use @userinfobot**
1. Open Telegram
2. Search for `@userinfobot`
3. Start a chat with it
4. It will send you your `CHAT_ID` (a number like `123456789`)

**Method 2: Use getUpdates API**
1. Send any message to your bot first
2. Visit this URL in your browser:
```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdatesimport requests
from flask import Flask
import os

app = Flask(__name__)

# ================= TELEGRAM =================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Replace with actual token
CHAT_ID = "YOUR_CHAT_ID"              # Replace with actual chat ID

@app.route('/')
def health():
    return "Bot is running", 200

@app.route('/test')
def test_telegram():
    """Test endpoint to send a message"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": "🧪 TEST MESSAGE - If you see this, Telegram works!"
        }
        response = requests.post(url, json=payload, timeout=10)
        return f"Response: {response.status_code} - {response.text}", 200
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting test server on port {port}")
    print(f"Visit: https://your-railway-url.up.railway.app/test")
    app.run(host="0.0.0.0", port=port)
```

**Deploy this and visit:** `https://your-railway-url.up.railway.app/test`

You should see either:
- ✅ "Response: 200" (success)
- ❌ An error message

---

## Step 2: Get Your Correct CHAT_ID

If the test fails, your `CHAT_ID` might be wrong. Here's how to get it:

**Method 1: Use @userinfobot**
1. Open Telegram
2. Search for `@userinfobot`
3. Start a chat with it
4. It will send you your `CHAT_ID` (a number like `123456789`)

**Method 2: Use getUpdates API**
1. Send any message to your bot first
2. Visit this URL in your browser:
```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
