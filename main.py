import os
import time
import signal
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# LOGGING для Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("🚀 === SVITLOBOT RAILWAY START ===")

# Railway бере змінні з Dashboard
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TAPO_EMAIL = os.environ.get("TAPO_USERNAME")
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD")
CLOUD_URL = "https://eu-wap.tplinkcloud.com"

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN обов'язковий!")
    exit(1)

# Глобальні змінні
cloud_token = None
device_id = None
last_state = None
power_off_at = None
app_instance = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def kyiv_datetime():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y %H:%M")

def cloud_login():
    global cloud_token
    if not TAPO_EMAIL or not TAPO_PASSWORD:
        logger.warning("⚠️ TAPO дані відсутні - без розетки")
        return False
    
    try:
        r = requests.post(CLOUD_URL, json={
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
            logger.info("✅ TP-Link OK")
            return True
        logger.error(f"❌ TP-Link: {r}")
    except Exception as e:
        logger.error(f"❌ TP-Link: {e}")
    return False

def fetch_device_id():
    global device_id
    if not cloud_token: return False
    
    try:
        r = requests.post(
            f"{CLOUD_URL}/?token={cloud_token}",
            json={"method": "getDeviceList"},
            timeout=20
        ).json()
        
        for d in r["result"]["deviceList"]:
            if "PLUG" in d.get("deviceType", "").upper():
                device_id = d["deviceId"]
                logger.info(f"✅ P110: {d.get('nickname')} (ID={device_id})")
                return True
        logger.warning("⚠️ Розетку не знайдено")
    except Exception as e:
        logger.error(f"❌ Пошук P110: {e}")
    return False

def power_present():
    if not device_id or not cloud_token: return True
    
    try:
        r = requests.post(
            f"{CLOUD_URL}/?token={cloud_token}",
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
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def power_job(context: ContextTypes.DEFAULT_TYPE):
    global last_state, power_off_at
    
    state = power_present()
    
    if state == last_state: return
    
    now = kyiv_time()
    
    if not state:
        power_off_at = time.time()
        msg = f"⚡ *СВІТЛО ЗНИКЛО*\n🕐 {now}"
        logger.warning(f"🚨 АВАРІЯ: {now}")
    else:
        minutes = int((time.time() - power_off_at) / 60) if power_off_at else 0
        msg = f"🔌 *СВІТЛО Є*\n🕐 {now}\n⏱️ Не було: {minutes} хв"
        logger.info(f"✅ ВІДНОВЛЕНО: {now}")
    
    await context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    last_state = state

def main():
    global app_instance
    
    # TP-Link (опціонально)
    tapo_ready = False
    if cloud_login():
        tapo_ready = fetch_device_id()
    
    logger.info("🤖 Telegram Bot...")
    app_instance = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app_instance.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
        handle_message
    ))
    
    if tapo_ready and app_instance.job_queue:
        app_instance.job_queue.run_repeating(power_job, interval=30, first=10)
        logger.info("⏰ P110 моніторинг запущено")
    
    logger.info("🎉 SVITLOBOT готовий! DTEK + P110")
    app_instance.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
