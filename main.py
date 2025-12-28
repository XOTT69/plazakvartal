import os
import time
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
    CommandHandler
)

# Railway logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("🚀 SVITLOBOT RAILWAY START")

# Railway Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TAPO_EMAIL = os.environ.get("TAPO_USERNAME")
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD")

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN required!")
    raise ValueError("BOT_TOKEN missing")

# Global state
cloud_token = None
device_id = None
last_state = None
power_off_at = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def cloud_login():
    global cloud_token
    if not TAPO_EMAIL or not TAPO_PASSWORD:
        logger.warning("⚠️ No TAPO credentials - P110 disabled")
        return False
    
    try:
        r = requests.post("https://eu-wap.tplinkcloud.com", json={
            "method": "login",
            "params": {
                "appType": "Tapo_Android",
                "cloudUserName": TAPO_EMAIL,
                "cloudPassword": TAPO_PASSWORD,
                "terminalUUID": "svitlobot"
            }
        }, timeout=20).json()
        
        if "result" in r and "token" in r["result"]:
            cloud_token = r["result"]["token"]
            logger.info("✅ TP-Link login OK")
            return True
        logger.error(f"❌ TP-Link login failed: {r}")
    except Exception as e:
        logger.error(f"❌ TP-Link error: {e}")
    return False

def fetch_device_id():
    global device_id
    if not cloud_token: return False
    
    try:
        r = requests.post(
            f"https://eu-wap.tplinkcloud.com/?token={cloud_token}",
            json={"method": "getDeviceList"},
            timeout=20
        ).json()
        
        devices = r.get("result", {}).get("deviceList", [])
        for d in devices:
            if "PLUG" in d.get("deviceType", "").upper():
                device_id = d["deviceId"]
                logger.info(f"✅ P110 found: {d.get('nickname', 'P110')} (ID={device_id})")
                return True
        logger.warning("⚠️ No P110 plug found")
    except Exception as e:
        logger.error(f"❌ Device search failed: {e}")
    return False

def power_present():
    if not device_id or not cloud_token: return True
    
    try:
        r = requests.post(
            f"https://eu-wap.tplinkcloud.com/?token={cloud_token}",
            json={
                "method": "passthrough",
                "params": {
                    "deviceId": device_id,
                    "requestData": '{"method":"get_device_info"}'
                }
            },
            timeout=10
        ).json()
        return bool(r.get("result", {}).get("responseData"))
    except:
        return False

def build_22_message(text: str):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return None
    header = lines[0]
    for line in lines:
        if "2.2" in line and ("Підгрупа" in line or "підгрупу" in line):
            return f"{header}\n\n📍 {line}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        logger.info("📨 DTEK 2.2 message forwarded")
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def power_job(context: ContextTypes.DEFAULT_TYPE):
    global last_state, power_off_at
    
    state = power_present()
    if state == last_state: return
    
    now = kyiv_time()
    
    if not state:
        power_off_at = time.time()
        msg = f"⚡ *СВІТЛО ЗНИКЛО*\n🕐 {now}"
        logger.warning(f"🚨 LIGHT OFF: {now}")
    else:
        minutes = int((time.time() - power_off_at) / 60) if power_off_at else 0
        msg = f"🔌 *СВІТЛО Є*\n🕐 {now}\n⏱️ Не було: {minutes} хв"
        logger.info(f"✅ LIGHT ON: {now} ({minutes}min offline)")
    
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")
    
    last_state = state

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Svitlobot запущено!")

def main():
    # TP-Link setup (optional)
    tapo_ready = False
    if cloud_login():
        tapo_ready = fetch_device_id()
    
    logger.info(f"🤖 Starting bot... P110: {'✅' if tapo_ready else '❌'}")
    
    # Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
        handle_message
    ))
    
    # P110 monitoring
    if tapo_ready:
        application.job_queue.run_repeating(power_job, interval=30, first=10)
        logger.info("⏰ P110 monitoring started (30s)")
    
    logger.info("🎉 Svitlobot ready! DTEK + P110")
    
    # Railway keep-alive
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
