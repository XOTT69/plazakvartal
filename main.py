import os
import time
import requests
import hmac
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

TUYA_ACCESS_ID = os.environ["TUYA_ACCESS_ID"]
TUYA_ACCESS_SECRET = os.environ["TUYA_ACCESS_SECRET"]
TUYA_DEVICE_ID = os.environ["TUYA_DEVICE_ID"]
TUYA_REGION = "eu"

CHECK_INTERVAL = 60  # seconds
REQUEST_TIMEOUT = 8
RETRY_COUNT = 2

# ================= STATE =================
last_state = None        # True / False
power_off_start = None   # datetime
last_online = True       # Tuya reachable

# ================= HELPERS =================
def kyiv_now():
    return datetime.now(ZoneInfo("Europe/Kyiv"))

def kyiv_str():
    return kyiv_now().strftime("%d.%m %H:%M")

def tuya_sign(url, params):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    payload = f"{url}?{query}"
    return hmac.new(
        TUYA_ACCESS_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

# ================= TUYA =================
def get_power_status():
    ts = str(int(time.time()))
    url = f"https://{TUYA_REGION}.tuya.com/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"

    params = {
        "access_id": TUYA_ACCESS_ID,
        "timestamp": ts,
    }

    sign = tuya_sign(url, params)

    headers = {
        "client_id": TUYA_ACCESS_ID,
        "t": ts,
        "sign": sign,
        "sign_method": "HMAC-SHA256",
    }

    for _ in range(RETRY_COUNT):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            data = r.json()

            if not data.get("success"):
                return None

            for s in data["result"]:
                if s["code"] == "switch_1":
                    return bool(s["value"])

            return None

        except Exception as e:
            print("Tuya error:", e)
            time.sleep(1)

    return None

# ================= MONITOR =================
async def monitor(context: ContextTypes.DEFAULT_TYPE):
    global last_state, power_off_start, last_online

    status = get_power_status()
    now = kyiv_now()

    # 🟡 Tuya offline
    if status is None:
        if last_online:
            last_online = False
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"🟡 Немає звʼязку з розеткою Tuya {kyiv_str()}"
            )
        return

    last_online = True

    # 🔴 Світло зникло
    if status is False and last_state is not False:
        power_off_start = now
        last_state = False
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"🔴 Світла нема {kyiv_str()}"
        )
        return

    # 🟢 Світло зʼявилось
    if status is True and last_state is not True:
        last_state = True
        if power_off_start:
            mins = int((now - power_off_start).total_seconds() / 60)
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"🟢 Світло Є! ({mins} хв без світла) {kyiv_str()}"
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"🟢 Світло Є! {kyiv_str()}"
            )
        power_off_start = None

# ================= COMMAND =================
async def status_cmd(update, context):
    state = get_power_status()

    if state is None:
        msg = "🟡 Немає звʼязку з Tuya"
    elif state:
        msg = f"🟢 Світло Є {kyiv_str()}"
    else:
        msg = f"🔴 Світла нема {kyiv_str()}"

    await update.message.reply_text(msg)

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("status", status_cmd))

    app.job_queue.run_repeating(
        monitor,
        interval=CHECK_INTERVAL,
        first=10
    )

    print("🚀 SvitloBot FULL VERSION RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
