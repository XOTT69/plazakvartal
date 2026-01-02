import os
import time
import requests
import hmac
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

print("🚀 SvitloBot UA - Aubess 20A - FIXED VERSION")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"  # or "us", "cn" - check your Tuya console [web:17]

# Global state tracking
last_power_on_time = None
last_status_check = None
power_off_start = None

def get_kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(base_url, params):
    params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    content = f"{base_url}?{params_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_power_status():
    global last_status_check
    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {
            "access_id": TUYA_ACCESS_ID,
            "timestamp": ts,
            "sign": tuya_sign(url.split("?")[0], {"access_id": TUYA_ACCESS_ID, "timestamp": ts})
        }
        headers = {"client_id": TUYA_ACCESS_ID, "sign": params["sign"], "t": ts, "sign_method": "HMAC-SHA256"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("success"):
            statuses = data["result"]
            for stat in statuses:
                if stat["code"] == "switch_1":  # or check your device DPS code [web:20]
                    is_on = stat["value"]
                    now = datetime.now(ZoneInfo("Europe/Kyiv"))
                    last_status_check = now
                    
                    if is_on:
                        global last_power_on_time, power_off_start
                        last_power_on_time = now
                        power_off_start = None
                        return True, 0
                    else:
                        if power_off_start is None:
                            power_off_start = now
                        outage_duration = int((now - power_off_start).total_seconds() / 60)
                        return False, outage_duration
        return None, 0
    except Exception as e:
        print(f"Tuya error: {e}")
        return None, 0

async def send_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int, force_channel=False):
    global last_power_on_time
    is_on, outage_mins = await get_power_status()
    
    now_str = get_kyiv_time()
    
    if is_on:
        msg = f"🟢 Світло Є! [{now_str}]"
        last_power_on_time = datetime.now(ZoneInfo("Europe/Kyiv"))
    else:
        if outage_mins == 0:
            msg = f"🔴 Світла нема [{now_str}]"
        else:
            msg = f"🔴 Світла нема {outage_mins}хв [{now_str}]"
    
    # Always send to channel on changes or force
    await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
    
    # Send to private chat if not channel
    if chat_id != CHANNEL_ID:
        await context.bot.send_message(chat_id=chat_id, text=msg)
    
    print(f"Status sent to {chat_id}: {msg}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_chat.id, False)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    if "2.2" in text.lower() or "світло" in text.lower():
        await send_status(context, update.effective_chat.id, True)

def main():
    if not all([BOT_TOKEN, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_DEVICE_ID]):
        print("❌ Missing env vars! Set: BOT_TOKEN, CHANNEL_ID, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_DEVICE_ID")
        return
    
    print("✅ Config OK - launching...")
    print(f"Device: {TUYA_DEVICE_ID[:8]}... Region: {TUYA_REGION}")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    
    print("🌟 Bot ready! Test /status")
    app.run_polling()

if __name__ == "__main__":
    main()
