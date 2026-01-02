import os
import tinytuya
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")
TUYA_IP = os.environ.get("TUYA_IP")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

print(f"🔌 tinytuya: {TUYA_IP}/{TUYA_DEVICE_ID}")

# Підключення
device = tinytuya.OutletDevice(TUYA_DEVICE_ID, TUYA_IP, local_key="ffffffff")
device.set_version(3.3)
device.logs = False

outage_start = None

def get_switch():
    try:
        if device.ping():
            status = device.status()
            print(f"Status: {status}")
            switch = status.get('switch_1', 'false')
            is_on = switch.lower() == 'true' or switch is True
            print(f"Switch_1: {switch} → {is_on}")
            return is_on
        print("❌ No ping")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def time_kyiv():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global outage_start
    
    is_on = get_switch()
    t = time_kyiv()
    
    if is_on:
        mins = 0
        if outage_start:
            mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - outage_start).total_seconds() / 60)
            outage_start = None
        msg = f"🟢 Світло Є! {t}"
        if mins: msg += f"\n⏱ Без світла: {mins}хв"
    else:
        if not outage_start:
            outage_start = datetime.now(ZoneInfo("Europe/Kyiv"))
        mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - outage_start).total_seconds() / 60)
        msg = f"🔴 Світла нема {mins}хв {t}"
    
    await context.bot.send_message(CHANNEL_ID, msg)
    await update.message.reply_text(msg)

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "2.2" in update.message.text.lower():
        await status_cmd(update, context)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("status", status_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))

print("🌟 tinytuya LAN ready!")
app.run_polling()
