import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram import Update

# Railway ENV
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WORKER_URL = os.environ.get("WORKER_URL")  # https://svitlo-tuya.твій.workers.dev
DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")  # bfa671762a871e5405rvq4
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

print(f"🚀 Bot: {DEVICE_ID[:8]} → {WORKER_URL}")

outage_start = None

def get_power_status():
    """Worker → Tuya"""
    try:
        resp = requests.get(f"{WORKER_URL}/status?device={DEVICE_ID}", timeout=8)
        data = resp.json()
        print(f"Tuya resp: {data}")
        
        if data.get("success"):
            for stat in data.get("result", []):
                if "switch" in stat["code"].lower():
                    val = stat["value"]
                    is_on = val is True or val == "true" or val == 1
                    print(f"Switch {stat['code']}: {val} → {is_on}")
                    return is_on
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global outage_start
    
    is_on = get_power_status()
    now = kyiv_time()
    
    if is_on:
        if outage_start:
            mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - outage_start).total_seconds() / 60)
            msg = f"🟢 Світло Є! {now}\n⏱ Без світла було: {mins}хв"
            outage_start = None
        else:
            msg = f"🟢 Світло Є! {now}"
    else:
        if outage_start is None:
            outage_start = datetime.now(ZoneInfo("Europe/Kyiv"))
        mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - outage_start).total_seconds() / 60)
        msg = f"🔴 Світла нема {mins}хв {now}"
    
    # Канал + чат
    await context.bot.send_message(CHANNEL_ID, msg)
    await update.message.reply_text(msg)
    print(msg)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if "2.2" in text.lower() or "світло" in text.lower():
        await status_command(update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🌟 Railway bot ready!")
    app.run_polling()

if __name__ == "__main__":
    main()
