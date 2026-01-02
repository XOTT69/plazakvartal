import os
import time
import asyncio
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

# Tuya Cloud (since platform.tuya.com setup)
TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")  # from Tuya app/platform
TUYA_REGION = "eu"  # Central Europe for UA

# Globals for outage tracking
last_power_state = None
power_off_time = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_sign(url, params, secret):
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    content = f"{url}?{params_str}"
    return hmac.new(secret.encode(), content.encode(), hashlib.sha256).hexdigest()

async def get_device_status():
    if not all([TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_DEVICE_ID]):
        return None
    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        sign = tuya_sign(url.split("?")[0], params, TUYA_ACCESS_SECRET)
        headers = {"client_id": TUYA_ACCESS_ID, "sign": sign, "t": ts, "sign_method": "HMAC-SHA256"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if data.get("success"):
            dps = data["result"][0]["value"]
            return dps.get("1", False)  # switch_1 bool [web:16][web:40]
        return None
    except:
        return None

def format_duration(seconds):
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"{mins}хв" if mins > 0 else f"{int(seconds)}с"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hours}г {mins}хв"

async def send_to_channel(text):
    try:
        await application.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=None)
    except:
        pass  # ignore errors

application = None

async def power_check(context: ContextTypes.DEFAULT_TYPE):
    global last_power_state, power_off_time
    power_on = await get_device_status()
    now = time.time()
    
    if power_on and last_power_state != True:
        last_power_state = True
        if power_off_time:
            duration = format_duration(now - power_off_time)
            await send_to_channel(f"🟢 Світло Є! Без світла було {duration} [{kyiv_time()}]")
        power_off_time = None
    elif not power_on and last_power_state != False:
        last_power_state = False
        power_off_time = now
        await send_to_channel(f"🔴 Світла нема [{kyiv_time()}]")
    
    # Also send to /status requests via context
    if context.job.data == "status":
        state = "🟢 Є світло" if power_on else "🔴 Нема світла"
        duration = format_duration(now - power_off_time) if power_off_time else "0хв"
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"{state}\nБез світла: {duration}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.run_once(power_check, 0, data="status", chat_id=update.effective_chat.id)

def build_22_message(text: str) -> str | None:
    lines = text.splitlines()
    header = None
    for line in lines:
        if line.strip():
            header = line
            break
    if header is None:
        return None

    start_22 = None
    for i, line in enumerate(lines):
        if "Підгрупа" in line and "2.2" in line:
            start_22 = i
            break

    if start_22 is not None:
        block = []
        for line in lines[start_22:]:
            if line.strip() == "" and block:
                break
            block.append(line)
        block = [l for l in block if l.strip()]
        header_lines = []
        for line in lines:
            if line.strip():
                header_lines.append(line)
                if len(header_lines) == 2:
                    break
        result_lines = header_lines + [""] + block
        return "\n".join(result_lines).strip()

    line_22 = None
    for line in lines:
        if "2.2" in line and "підгрупу" in line:
            line_22 = line
            break

    if line_22:
        if line_22 == header:
            return line_22
        return f"{header}\n{line_22}"

    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    text = msg.text or msg.caption or ""
    if not text:
        return

    payload = build_22_message(text)
    if payload:
        # Append power status to 2.2 messages
        power_on = await get_device_status()
        state = "🟢 Є світло" if power_on else "🔴 Нема світла"
        payload += f"\n\n💡 {state}"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)
        return

async def main():
    global application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", status_cmd))

    # Periodic check every 30s
    app.job_queue.run_repeating(power_check, interval=30, first=5)

    application = app
    print("🚀 Bot started with Tuya monitoring")
    app.run_polling()

if __name__ == "__main__":
    main()
