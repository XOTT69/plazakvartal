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

print("🚀 SvitloBot 30s mode...")

# ================== ENV ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "")
TUYA_REGION = "eu"

print(f"TUYA_DEVICE_ID length: {len(TUYA_DEVICE_ID)}")

# ================== STATE ==================
last_power_state = None     # None = ще не ініціалізовано
power_off_time = None

# ================== HELPERS ==================
def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def format_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}г {m}хв"
    return f"{m}хв"

def tuya_sign(base_url, params):
    params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    content = f"{base_url}?{params_str}"
    return hmac.new(
        TUYA_ACCESS_SECRET.encode(),
        content.encode(),
        hashlib.sha256
    ).hexdigest()

async def get_power_status():
    if not all([TUYA_DEVICE_ID, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET]):
        return None

    try:
        ts = str(int(time.time()))
        url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        params = {"access_id": TUYA_ACCESS_ID, "timestamp": ts}
        sign = tuya_sign(url, params)

        headers = {
            "client_id": TUYA_ACCESS_ID,
            "sign": sign,
            "t": ts,
            "sign_method": "HMAC-SHA256",
        }

        resp = requests.get(url, params=params, headers=headers, timeout=5).json()
        if resp.get("success"):
            # 🔌 беремо перший DP (розетка)
            return bool(resp["result"][0]["value"])
    except Exception as e:
        print("❌ Tuya error:", e)

    return None

# ================== CORE ==================
async def check_power(context: ContextTypes.DEFAULT_TYPE):
    global last_power_state, power_off_time

    power_on = await get_power_status()
    if power_on is None:
        return

    now = time.time()

    # 🔹 Перший запуск — тільки ініціалізація
    if last_power_state is None:
        last_power_state = power_on
        if not power_on:
            power_off_time = now
        print(f"⚡ Init state: {'ON' if power_on else 'OFF'}")
        return

    # 🔹 Без змін
    if power_on == last_power_state:
        return

    # 🔹 Зміна стану
    if power_on:
        duration = ""
        if power_off_time:
            duration = format_duration(now - power_off_time)
            power_off_time = None

        msg = f"🟢 Світло Є! {kyiv_time()}"
        if duration:
            msg += f"\n⏱ Без світла було: {duration}"
    else:
        power_off_time = now
        msg = f"🔴 Світла нема {kyiv_time()}"

    last_power_state = power_on

    await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
    print(f"📢 {msg}")

# ================== 2.2 PARSER ==================
def build_22_message(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    header = lines[0]
    for line in lines:
        if "2.2" in line:
            return f"{header}\n\n{line}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)

    if payload:
        power = await get_power_status()
        emoji = "🟢 Є" if power else "🔴 НІ"
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"{payload}\n\n💡 {emoji}"
        )

    await check_power(context)

# ================== COMMANDS ==================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    power = await get_power_status()
    if power is None:
        await update.message.reply_text("❌ Немає даних")
        return

    if not power and power_off_time:
        duration = format_duration(time.time() - power_off_time)
    else:
        duration = "є світло"

    await update.message.reply_text(
        f"💡 {'🟢 Є' if power else '🔴 НІ'}\n⏱ Без світла: {duration}"
    )

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handle_message
        )
    )

    app.job_queue.run_repeating(check_power, interval=30, first=10)
    print("⏰ Monitoring every 30s")
    print("🌟 LIVE!")

    app.run_polling()

if __name__ == "__main__":
    main()
