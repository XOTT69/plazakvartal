import os
import time
import requests
import hmac
import hashlib
import threading
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

print("🚀 SvitloBot 30s mode - NO ASYNC!")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"

print(f"TUYA_DEVICE_ID: {len(TUYA_DEVICE_ID)} chars")

last_power_state = False
power_off_time = None
monitor_running = False

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(base_url, params):
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    content = f"{base_url}?{params_str}"
    return hmac.new(TUYA_ACCESS_SECRET.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_power_status():
    if not all([TUYA_DEVICE_ID, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET]):
        return None
    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        sign = tuya_sign(url.split("?")[0], params)
        headers = {"client_id": TUYA_ACCESS_ID, "sign": sign, "t": ts, "sign_method": "HMAC-SHA256"}
        resp = requests.get(url, params=params, headers=headers, timeout=5).json()
        if resp.get("success"):
            return bool(resp["result"][0]["value"].get("1", False))
    except:
        pass
    return None

def format_duration(seconds):
    h, m = divmod(int(seconds), 3600)
    if h > 0:
        return f"{h}г {m}хв"
    return f"{m}хв"

async def send_status_message(msg):
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await app.bot.send_message(chat_id=CHANNEL_ID, text=msg)

async def check_power():
    global last_power_state, power_off_time
    now = time.time()
    power_on = await get_power_status()

    if power_on == last_power_state:
        return

    state = "🟢 Світло Є!" if power_on else "🔴 Світла нема"
    duration = ""

    if power_on and power_off_time is not None:
        duration = format_duration(now - power_off_time)
        power_off_time = None
    elif not power_on:
        power_off_time = now

    last_power_state = power_on
    msg = f"{state} {kyiv_time()}"
    if duration:
        msg += f"\n⏱ Без світла було: {duration}"

    await send_status_message(msg)
    print(f"🚨 {msg}")

def monitor_thread():
    global monitor_running
    while monitor_running:
        asyncio.run(check_power())
        time.sleep(30)

def build_22_message(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    header = lines[0]
    for i, line in enumerate(lines):
        if "2.2" in line:
            return f"{header}\n\n{line}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        power = await get_power_status()
        emoji = "🟢 Є" if power else "🔴 НІ"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"{payload}\n\n💡 {emoji}")

    await check_power()

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_power_state, power_off_time

    power = await get_power_status()
    if power is not None:
        last_power_state = power

    now = time.time()
    if last_power_state:
        text = "💡 🟢 Є"
    else:
        if power_off_time is not None:
            duration = format_duration(now - power_off_time)
            text = f"💡 🔴 Без світла: {duration}"
        else:
            text = "💡 🔴 Без світла (перше)"

    await update.message.reply_text(text)

def main():
    global monitor_running
    monitor_running = True
    
    # Запускаємо моніторинг в окремому потоці
    monitor = threading.Thread(target=monitor_thread, daemon=True)
    monitor.start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", status_cmd))
    
    print("⏰ 30s monitoring → THREAD OK!")
    print("🌟 LIVE!")
    app.run_polling()

if __name__ == "__main__":
    main()
