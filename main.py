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

print("🚀 SvitloBot UA - FIXED OUTAGE TIMER")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"  # zmień на "us"/"cn" якщо потрібно

# Global state - CRITICAL FIX: persist across checks
power_off_start_time = None  # Коли ВПЕРШЕ вимкнули
last_check_time = None
last_power_state = None

def get_kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(base_url, params):
    params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    content = f"{base_url}?{params_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_power_status():
    global last_check_time, last_power_state
    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {
            "access_id": TUYA_ACCESS_ID,
            "timestamp": ts,
        }
        sign_params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        params["sign"] = tuya_sign(url.split("?")[0], sign_params)
        
        headers = {
            "client_id": TUYA_ACCESS_ID, 
            "sign": params["sign"], 
            "t": ts, 
            "sign_method": "HMAC-SHA256"
        }
        
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("success"):
            statuses = data["result"]
            for stat in statuses:
                if stat["code"] == "switch_1":  # DP code для Aubess
                    current_state = stat["value"] == True  # bool!
                    now = datetime.now(ZoneInfo("Europe/Kyiv"))
                    last_check_time = now
                    
                    return current_state, now
        return None, now
    except Exception as e:
        print(f"Tuya error: {e}")
        return None, datetime.now(ZoneInfo("Europe/Kyiv"))

def calculate_outage():
    global power_off_start_time
    if power_off_start_time:
        now = datetime.now(ZoneInfo("Europe/Kyiv"))
        duration = int((now - power_off_start_time).total_seconds() / 60)
        return duration
    return 0

async def send_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int, is_change=False):
    global power_off_start_time, last_power_state
    
    is_on, check_time = await get_power_status()
    if is_on is None:
        await context.bot.send_message(chat_id=chat_id, text="❌ Tuya помилка - спробуй пізніше")
        return
    
    now_str = get_kyiv_time()
    outage_mins = calculate_outage()
    
    # DETECT CHANGE для сповіщення
    state_changed = last_power_state is not None and last_power_state != is_on
    last_power_state = is_on
    
    if is_on:
        # Світло УВІМКНУЛИ
        if state_changed or power_off_start_time:
            outage_str = f"⏱ Без світла було: {outage_mins}хв" if outage_mins > 0 else ""
            msg = f"🟢 Світло Є! {now_str}\n{outage_str}".strip()
            power_off_start_time = None  # reset
        else:
            msg = f"🟢 Світло Є! {now_str}"
    else:
        # Світла НЕМАЄ
        if power_off_start_time is None:
            # ВПЕРШЕ вимикаємо - фіксуємо початок
            power_off_start_time = check_time
        
        if outage_mins == 0:
            msg = f"🔴 Світла нема {now_str}"
        else:
            msg = f"🔴 Світла нема {outage_mins}хв {now_str}"
    
    # Завжди в канал при ЗМІНАХ, в приват завжди
    if state_changed or is_change:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"🔄 CHANGE! {msg}")
    
    await context.bot.send_message(chat_id=chat_id, text=msg)
    print(f"📡 Status: {is_on} | Outage: {outage_mins}m")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_chat.id, True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or update.message.caption or "").lower()
    if any(word in text for word in ["2.2", "світло", "status"]):
        await send_status(context, update.effective_chat.id, True)

def main():
    missing = [v for v in ["BOT_TOKEN", "TUYA_ACCESS_ID", "TUYA_ACCESS_SECRET", "TUYA_DEVICE_ID"] 
               if not os.environ.get(v)]
    if missing:
        print(f"❌ Missing: {missing}")
        return
    
    print("✅ FIXED: Outage timer + clean format")
    print(f"🚀 Device: {TUYA_DEVICE_ID[:8]}...")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    
    print("🌟 Ready! /status тест")
    app.run_polling()

if __name__ == "__main__":
    main()
