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
from telegram.request import HTTPXRequest  # ✅ FIX для конфлікту

print("🚀 SvitloBot UA - FIXED HTTPX CONFLICT")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"

# Global state
power_off_start_time = None
last_power_state = None
last_check_time = None

def get_kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(base_string, params):
    """FIX: правильний Tuya sign"""
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    string_to_sign = f"{base_string}?{params_str}"
    return hmac.new(
        TUYA_ACCESS_SECRET.encode(), 
        string_to_sign.encode(), 
        hashlib.sha256
    ).hexdigest()

async def get_power_status():
    global last_check_time, last_power_state
    try:
        ts = str(int(time.time() * 1000))  # milliseconds!
        path = f"/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        base_url = f"https://{TUYA_REGION}.tuya.com{path}"
        
        params = {
            "access_id": TUYA_ACCESS_ID,
            "timestamp": ts,
        }
        params["sign"] = tuya_sign(path, params)  # path only!
        
        resp = requests.get(base_url, params=params, timeout=10)
        data = resp.json()
        
        print(f"Tuya response: {data.get('success', False)}")  # debug
        
        if data.get("success"):
            for status in data["result"]:
                if status["code"] == "switch_1":
                    is_on = status["value"] == True
                    now = datetime.now(ZoneInfo("Europe/Kyiv"))
                    last_check_time = now
                    return is_on, now
        return None, now
    except Exception as e:
        print(f"Tuya error: {e}")
        return None, datetime.now(ZoneInfo("Europe/Kyiv"))

def get_outage_minutes():
    global power_off_start_time
    if power_off_start_time:
        now = datetime.now(ZoneInfo("Europe/Kyiv"))
        return max(0, int((now - power_off_start_time).total_seconds() / 60))
    return 0

async def send_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int, force_channel=False):
    global power_off_start_time, last_power_state
    
    is_on, check_time = await get_power_status()
    if is_on is None:
        msg = "❌ Помилка Tuya API"
        await context.bot.send_message(chat_id=chat_id, text=msg)
        return
    
    outage_mins = get_outage_minutes()
    now_str = get_kyiv_time()
    state_changed = last_power_state is not None and last_power_state != is_on
    last_power_state = is_on
    
    if is_on:
        # 🟢 Світло з'явилось
        power_off_start_time = None
        outage_str = f"⏱ Без світла: {outage_mins}хв" if outage_mins > 0 else ""
        msg = f"🟢 Світло Є! {now_str}\n{outage_str}".strip()
    else:
        # 🔴 Світла нема
        if power_off_start_time is None:
            power_off_start_time = check_time
        
        if outage_mins == 0:
            msg = f"🔴 Світла нема {now_str}"
        else:
            msg = f"🔴 Світла нема {outage_mins}хв {now_str}"
    
    # Логіка сповіщень
    if state_changed or force_channel:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"🔄 ЗМІНА! {msg}")
    
    await context.bot.send_message(chat_id=chat_id, text=msg)
    print(f"📡 {is_on} | {outage_mins}хв")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /status - показати стан """
    await send_status(context, update.effective_chat.id, True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or update.message.caption or "").lower()
    if any(kw in text for kw in ["2.2", "світло", "статус"]):
        await send_status(context, update.effective_chat.id, True)

def main():
    required = ["BOT_TOKEN", "TUYA_ACCESS_ID", "TUYA_ACCESS_SECRET", "TUYA_DEVICE_ID"]
    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        print("❌ Відсутні:", ", ".join(missing))
        return
    
    print("✅ Всі змінні OK")
    print(f"Device ID: {TUYA_DEVICE_ID[:10]}...")
    
    # ✅ FIX: явний HTTPXRequest
    request = HTTPXRequest()
    app = ApplicationBuilder().token(BOT_TOKEN).http_version("1.1").request(request).build()
    
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    
    print("🚀 Bot запущено! Тест: /status")
    app.run_polling()

if __name__ == "__main__":
    main()
