import os
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update

# tinytuya після requirements!
try:
    import tinytuya
    TINYTUYA_OK = True
except ImportError:
    TINYTUYA_OK = False
    print("❌ tinytuya НЕ встановлено - перевір requirements.txt")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")
TUYA_IP = os.environ.get("TUYA_IP")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

print(f"🔌 IP: {TUYA_IP} ID: {TUYA_DEVICE_ID}")

device = None
outage_start = None

def init_device():
    global device
    if TINYTUYA_OK and TUYA_DEVICE_ID and TUYA_IP:
        device = tinytuya.OutletDevice(TUYA_DEVICE_ID, TUYA_IP, "ffffffff")
        device.set_version(3.3)
        device.logs = False
        print("✅ tinytuya device OK")
        return True
    return False

def get_power():
    if not device or not device.ping():
        print("❌ No device/ping")
        return False
    
    try:
        status = device.status()
        print(f"📡 Status: {status}")
        sw = status.get('switch_1', False)
        is_on = sw is True or str(sw).lower() == 'true'
        print(f"💡 switch_1={sw} → {is_on}")
        return is_on
    except Exception as e:
        print(f"❌ Status error: {e}")
        return False

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global outage_start
    
    if not init_device():
        await update.message.reply_text("❌ tinytuya не працює")
        return
    
    is_on = get_power()
    t = kyiv_time()
    
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "2.2" in update.message.text.lower():
        await status_cmd(update, context)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN!")
        exit()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🌟 tinytuya bot ready!")
    app.run_polling()
