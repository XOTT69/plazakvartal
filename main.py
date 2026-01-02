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

print("🚀 SvitloBot UA - RAILWAY 100% GREEN")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"

# Global outage tracker
power_off_start = None
last_state = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_signature(path, params):
    p_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign_str = f"{path}?{p_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

def tuya_status():
    try:
        ts = str(int(time.time_ns() // 1_000_000))  # ms
        path = f"/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        params["sign"] = tuya_signature(path, params)
        
        url = f"https://{TUYA_REGION}.tuya.com{path}"
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        
        print(f"Tuya: {data.get('success')}")
        
        if data.get("success"):
            for s in data["result"]:
                if s["code"] == "switch_1":
                    return s["value"] == True
        
        return None
    except:
        return None

def outage_duration():
    if power_off_start:
        now = datetime.now(ZoneInfo("Europe/Kyiv"))
        mins = int((now - power_off_start).total_seconds() / 60)
        return max(0, mins)
    return 0

async def send_status_msg(context: ContextTypes.DEFAULT_TYPE, chat_id, to_channel=False):
    global power_off_start, last_state
    
    power_on = tuya_status()
    if power_on is None:
        await context.bot.send_message(chat_id=chat_id, text="❌ Tuya недоступний")
        return
    
    outage_min = outage_duration()
    time_str = kyiv_time()
    changed = last_state is not None and last_state != power_on
    last_state = power_on
    
    if power_on:
        power_off_start = None
        extra = f"\n⏱ Без світла: {outage_min}хв" if outage_min else ""
        msg = f"🟢 Світло Є! {time_str}{extra}"
    else:
        if power_off_start is None:
            power_off_start = datetime.now(ZoneInfo("Europe/Kyiv"))
        mins_text = f"{outage_min}хв " if outage_min else ""
        msg = f"🔴 Світла нема {mins_text}{time_str}"
    
    if changed or to_channel:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"🔄 CHANGE → канал: {msg}")
    
    await context.bot.send_message(chat_id=chat_id, text=msg)
    print(f"Status: {'🟢' if power_on else '🔴'} | {outage_min}хв")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status_msg(context, update.effective_chat.id, True)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or update.message.caption or "").lower()
    if "2.2" in text or "світло" in text or "статус" in text:
        await send_status_msg(context, update.effective_chat.id, True)

def main():
    vars_check = {
        "BOT_TOKEN": BOT_TOKEN,
        "TUYA_ACCESS_ID": TUYA_ACCESS_ID, 
        "TUYA_ACCESS_SECRET": TUYA_ACCESS_SECRET,
        "TUYA_DEVICE_ID": TUYA_DEVICE_ID
    }
    
    missing = [k for k, v in vars_check.items() if not v]
    if missing:
        print("❌ Потрібно:", ", ".join(missing))
        return
    
    print("✅ ✅ ✅ ВСІ ЗМІННІ ОК!")
    print(f"🚀 {TUYA_DEVICE_ID[:8]}...")
    
    # ✅ 100% Railway PTB 21.7 - БЕЗ request/http_version!
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, message_handler))
    
    print("🌟 Bot готовий! /status")
    app.run_polling()

if __name__ == "__main__":
    main()
