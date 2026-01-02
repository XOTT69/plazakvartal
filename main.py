import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WORKER_URL = "https://patient-rice-f0ea.mikolenko-anton1.workers.dev"
DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))

print(f"🚀 https://patient-rice-f0ea.mikolenko-anton1.workers.dev + {DEVICE_ID}")

outage_start = None

def get_power():
    try:
        r = requests.get(f"{WORKER_URL}/status?device={DEVICE_ID}", timeout=8)
        data = r.json()
        print(f"Worker: {data}")
        
        if data.get("success"):
            for s in data["result"]:
                if "switch" in s["code"].lower():
                    val = s["value"]
                    is_on = val is True or str(val).lower() == "true"
                    print(f"✅ {s['code']}: {val} = {is_on}")
                    return is_on
        return False
    except Exception as e:
        print(f"❌ {e}")
        return False

def now_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global outage_start
    
    power_on = get_power()
    t = now_time()
    
    if power_on:
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

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "2.2" in update.message.text:
        await status_cmd(update, context)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("status", status_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("🌟 Railway + Worker ready!")
app.run_polling()
