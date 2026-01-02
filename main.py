import os
import time
import requests
import hmac
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

print("🚀 Starting SvitloBot...")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"

print(f"DEBUG: TUYA_DEVICE_ID='{TUYA_DEVICE_ID[:8]}...' ({len(TUYA_DEVICE_ID)})")
print(f"DEBUG: Access len={len(TUYA_ACCESS_ID)}, Secret len={len(TUYA_ACCESS_SECRET)}")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN missing!")
    raise ValueError("BOT_TOKEN required")

last_power_state = False
power_off_time = time.time()

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(base_url, params):
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    content = f"{base_url}?{params_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_power_status():
    if not all([TUYA_DEVICE_ID, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET]):
        print("❌ Tuya config missing")
        return None
    try:
        print("🔍 Checking Tuya...")
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        sign = tuya_sign(url.split("?")[0], params)
        headers = {
            "client_id": TUYA_ACCESS_ID, 
            "sign": sign, 
            "t": ts, 
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        print(f"Tuya response: {data.get('success')}")
        if data.get("success"):
            dps = data["result"][0]["value"]
            power_on = dps.get("1", False)
            print(f"Power: {power_on}")
            return bool(power_on)
    except Exception as e:
        print(f"Tuya error: {e}")
    return None

def format_duration(seconds):
    h, m = divmod(int(seconds), 3600)
    m, s = divmod(m, 60)
    if h > 0: return f"{h}г{m}хв"
    if m > 0: return f"{m}хв"
    return f"{s}с"

async def send_status(context, chat_id=CHANNEL_ID, full=False):
    global last_power_state, power_off_time
    now = time.time()
    power_on = await get_power_status()
    
    state = "🟢 Світло Є!" if power_on else "🔴 Світла нема"
    duration = ""
    
    if power_on and not last_power_state:
        if power_off_time:
            duration = format_duration(now - power_off_time)
        last_power_state = True
        power_off_time = None
    elif not power_on and last_power_state:
        last_power_state = False
        power_off_time = now
    
    if power_off_time and full:
        duration = format_duration(now - power_off_time)
    
    msg = f"{state} [{kyiv_time()}]"
    if duration:
        msg += f"\n⏱ Без світла: {duration}"
    
    await context.bot.send_message(chat_id=chat_id, text=msg)
    print(f"Sent: {msg}")

def build_22_message(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if (line := line.strip())]
    if not lines: return None
    
    header = lines[0]
    for i, line in enumerate(lines):
        if "Підгрупа 2.2" in line:
            block = lines[i:i+5]
            return f"{header}\n\n" + "\n".join(block)
        if "2.2 підгрупу" in line:
            return f"{header}\n\n{line}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or update.message.caption or "")
    payload = build_22_message(text)
    
    if payload:
        await send_status(context, CHANNEL_ID, False)
        payload += "\n\n💡 "
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)
    else:
        await send_status(context, update.effective_chat.id, True)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_chat.id, True)

def main():
    print("✅ All set, launching...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", status_cmd))
    print("🌟 Bot ready! Test /status")
    app.run_polling()

if __name__ == "__main__":
    main()
