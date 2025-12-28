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

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("🚀 === SVITLOBOT ФІНАЛЬНИЙ СТАРТ ===")

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TAPO_EMAIL = os.environ.get("TAPO_USERNAME")
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD")
CLOUD_URL = "https://eu-wap.tplinkcloud.com"

# Валідація обов'язкових параметрів
if not all([BOT_TOKEN, TAPO_EMAIL, TAPO_PASSWORD]):
    logger.error("❌ Відсутні обов'язкові змінні оточення: BOT_TOKEN, TAPO_USERNAME, TAPO_PASSWORD")
    raise RuntimeError("Missing required environment variables")

# Глобальні змінні стану
cloud_token = None
device_id = None
last_state = None
power_off_at = None
app_instance = None

# ================== UTIL ==================
def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def kyiv_datetime():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y %H:%M:%S")

# ================== TP-LINK CLOUD ==================
def cloud_login(max_retries=3):
    global cloud_token
    logger.info("🔌 TP-Link логін...")
    
    for attempt in range(max_retries):
        try:
            r = requests.post(
                CLOUD_URL,
                json={
                    "method": "login",
                    "params": {
                        "appType": "Tapo_Android",
                        "cloudUserName": TAPO_EMAIL,
                        "cloudPassword": TAPO_PASSWORD,
                        "terminalUUID": "svitlobot"
                    }
                },
                timeout=20
            ).json()
            
            if "result" in r and "token" in r["result"]:
                cloud_token = r["result"]["token"]
                logger.info("✅ TP-Link логін успішний")
                return True
            else:
                error_msg = r.get("error_code", "Unknown error")
                logger.error(f"❌ Помилка логіна TP-Link: {error_msg}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"⏳ Повторна спроба через {wait_time}с...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError("TP-Link Login Failed")
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Помилка підключення (спроба {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                raise RuntimeError("TP-Link Connection Failed")
    
    return False

def fetch_device_id(max_retries=3):
    global device_id
    logger.info("🔍 Шукаємо розетку P110...")
    
    if not cloud_token:
        logger.error("❌ Немає токена!")
        return False
    
    for attempt in range(max_retries):
        try:
            r = requests.post(
                f"{CLOUD_URL}/?token={cloud_token}",
                json={"method": "getDeviceList"},
                timeout=20
            ).json()
            
            devices = r.get("result", {}).get("deviceList", [])
            logger.info(f"📱 Пристроїв: {len(devices)}")
            
            for d in devices:
                device_type = d.get("deviceType", "").upper()
                nickname = d.get("nickname", "Unknown")
                logger.info(f"  → {nickname}: {device_type}")
                
                if "PLUG" in device_type or "P110" in device_type:
                    device_id = d["deviceId"]
                    logger.info(f"✅ РОЗЕТКА: {nickname} (ID={device_id})")
                    return True
            
            logger.warning("⚠️ Розеток не знайдено")
            return False
        
        except Exception as e:
            logger.warning(f"⚠️ Помилка пошуку (спроба {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return False

def power_present(max_retries=2):
    if not device_id or not cloud_token:
        return True
    
    for attempt in range(max_retries):
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
            
            has_response = bool(r.get("result", {}).get("responseData"))
            return has_response
        
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
    
    return True

# ================== DTEK PARSER ==================
def build_22_message(text: str):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return None
    
    header = lines[0]
    for line in lines:
        if "2.2" in line and any(kw in line for kw in ["Підгрупа", "підгрупу", "підгрупи"]):
            return f"{header}\n\n📍 {line}"
    return None

# ================== TELEGRAM ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def power_job(context: ContextTypes.DEFAULT_TYPE):
    global last_state, power_off_at
    
    state = power_present()
    
    if state == last_state:
        return
    
    now_time = kyiv_time()
    
    if not state:
        power_off_at = time.time()
        msg = f"⚡ *СВІТЛО ЗНИКЛО*\n🕐 {now_time}\n📍 {kyiv_datetime()}"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        logger.warning(f"🚨 АВАРІЯ: {now_time}")
    else:
        minutes = int((time.time() - power_off_at) / 60) if power_off_at else 0
        msg = f"🔌 *СВІТЛО ВІДНОВЛЕНО*\n🕐 {now_time}\n⏱️ Без світла: *{minutes} хв*"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        logger.info(f"✅ ВІДНОВЛЕНО: {now_time}")
    
    last_state = state

def signal_handler(sig, frame):
    logger.info("🛑 Завершення...")
    if app_instance:
        app_instance.stop()
    exit(0)

# ================== MAIN ==================
def main():
    global app_instance
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # TP-Link
    try:
        cloud_login()
        tapo_ready = fetch_device_id()
        logger.info("✅ Tapo OK" if tapo_ready else "⚠️ Без розетки")
    except Exception as e:
        logger.error(f"❌ Tapo: {e}")
    
    # Telegram
    app_instance = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app_instance.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
        handle_message
    ))
    
    if tapo_ready and app_instance.job_queue:
        app_instance.job_queue.run_repeating(power_job, interval=30, first=10)
        logger.info("⏰ JobQueue запущено")
    
    logger.info("🎉 Бот готовий!")
    app_instance.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
