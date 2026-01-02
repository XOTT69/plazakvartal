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

CHECK_INTERVAL = 60            # сек
REQUEST_TIMEOUT = 8
RETRY_COUNT = 2
CONFIRMATIONS_REQUIRED = 2    # антифлапінг
POWER_THRESHOLD_W = 2.0       # >2W = світло є

# ================= STATE =================
last_state = None             # True / False
candidate_state = None
candidate_count = 0
power_off_start = None

# ================= HELPERS =================
def kyiv_now():
    return datetime.now(ZoneInfo("Europe/Kyiv"))

def kyiv_str():
    return kyiv_now().strftime("%d.%m %H:%M")

def format_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} хв"
    h = minutes // 60
    m = minutes % 60
    return f"{h} год {m} хв"

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
    """
    Повертає:
      (True, watts)  -> світло є
      (False, watts) -> світла нема
      (None, None)   -> тимчасово недоступно
    """
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
            r = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            data = r.json()

            if not data.get("success"):
                return None, None

            watts = None
            switch_state = None

            for s in data["result"]:
                code = s.get("code")
                value = s.get("value")

                # 🔑 Aubess / Tuya: можливі коди потужності
                if code in ("cur_power", "power", "power_total"):
                    watts = float(value) / 10.0   # деци-вати → W
                elif code == "add_ele":
                    watts = float(value)          # вже в W
                elif code == "switch_1":
                    switch_state = bool(value)

            # 🎯 Пріоритет: ватти
            if watts is not None:
                return (watts > POWER_THRESHOLD_W), watts

            # 🔁 Fallback: switch
            if switch_state is not None:
                return switch_state, 0.0

            return None, None

        except Exception:
            time.sleep(1)

    return None, None

# ================= MONITOR =================
async def monitor(context: ContextTypes.DEFAULT_TYPE):
    global last_state, candidate_state, candidate_count, power_off_start

    status, watts = get_power_status()
    now = kyiv_now()

    # ❌ Tuya/DNS глюк → мовчимо
    if status is None:
        return

    # Антифлапінг
    if status != candidate_state:
        candidate_state = status
        candidate_count = 1
        return
    else:
        candidate_count += 1

    if candidate_count < CONFIRMATIONS_REQUIRED:
        return

    # 🔴 Світло зникло
    if status is False and last_state is not False:
        last_state = False
        power_off_start = now

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
            duration = format_minutes(mins)
            msg = (
                f"🟢 Світло Є!\n"
                f"Не було: {duration}\n"
                f"Споживання: {watts:.1f} W\n"
                f"{kyiv_str()}"
            )
        else:
            msg = (
                f"🟢 Світло Є!\n"
                f"Споживання: {watts:.1f} W\n"
                f"{kyiv_str()}"
            )

        power_off_start = None

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg
        )

# ================= COMMAND =================
async def status_cmd(update, context):
    status, watts = get_power_status()

    if status is None:
        msg = "ℹ️ Статус тимчасово недоступний"
    elif status:
        msg = (
            f"🟢 Світло Є\n"
            f"Споживання: {watts:.1f} W\n"
            f"{kyiv_str()}"
        )
    else:
        msg = (
            f"🔴 Світла нема\n"
            f"Споживання: {watts:.1f} W\n"
            f"{kyiv_str()}"
        )

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

    print("🚀 SvitloBot FINAL AUBESS 20A WATT-BASED VERSION RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
