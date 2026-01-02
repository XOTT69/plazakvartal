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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003534080985

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")
TUYA_REGION = "eu"

last_power_state = False
power_off_time = time.time()

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(url, params):
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    content = f"{url}?{params_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_power_status():
    if not TUYA_DEVICE_ID:
        return None
    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        sign = tuya_sign(url.split("?")[0], params)
        headers = {"client_id": TUYA_ACCESS_ID, "sign": sign, "t": ts, "sign_method": "HMAC-SHA256"}
        resp = requests.get(url, params=params, headers=headers, timeout=10).json()
        if resp.get("success"):
            return resp["result"][0]["value"].get("1", False)
    except:
        pass
    return None

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}г {m}хв"
    return f"{m}хв"

async def send_status(context, chat_id=CHANNEL_ID, with_duration=True):
    power_on = await get_power_status()
    global last_power_state, power_off_time
    now = time.time()
    
    state_emoji = "🟢 Є світло" if power_on else "🔴 Нема світла"
    duration = ""
    if power_on and last_power_state == False:
        duration = format_duration(now - power_off_time)
        last_power_state = True
        power_off_time = None
    elif not power_on and last_power_state == True:
        last_power_state = False
        power_off_time = now
    
    if with_duration and power_off_time:
        duration = format_duration(now - power_off_time)
    
    msg = f"{state_emoji} [{kyiv_time()}]"
    if duration:
        msg += f"\nБез світла: {duration}"
    
    await context.bot.send_message(chat_id=chat_id, text=msg)

def build_22_message(text: str) -> str | None:
    lines = text.splitlines()
    header = next((line.strip() for line in lines if line.strip()), None)
    if not header:
        return None
    for i, line in enumerate(lines):
        if "Підгрупа" in line and "2.2" in line:
            block = [l.strip() for l in lines[i:] if (l := l.strip())]
            return f"{header}\n\n" + "\n".join(block[:5])
        if "2.2" in line and "підгрупу" in line:
            return f"{header}\n{line}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        await send_status(context, CHANNEL_ID, False)
        payload += "\n\n💡 "
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)
        return
    # Any message - quick status check
    await send_status(context, update.effective_chat.id)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_chat.id, True)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", status_cmd))
    print("🚀 Bot started - no job_queue")
    app.run_polling()

if __name__ == "__main__":
    main()
