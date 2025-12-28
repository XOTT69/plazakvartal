import os
import time
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

print("🚀 === SVITLOBOT ФІНАЛЬНИЙ СТАРТ ===")

# ================== CONFIG ==================
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TAPO_EMAIL = os.environ["TAPO_USERNAME"]
TAPO_PASSWORD = os.environ["TAPO_PASSWORD"]
CLOUD_URL = "https://eu-wap.tplinkcloud.com"

# Глобальні змінні стану
cloud_token = None
device_id = None
last_state = None
power_off_at = None

# ================== UTIL ==================
def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

# ================== TP-LINK CLOUD ==================
def cloud_login():
    global cloud_token
    print("🔌 TP-Link логін...")
    try:
        r = requests.post(CLOUD_URL, json={
            "method": "login",
            "params": {
                "appType": "Tapo_Android",
                "cloudUserName": TAPO_EMAIL,
                "cloudPassword": TAPO_PASSWORD,
                "terminalUUID": "svitlobot"
            }
        }, timeout=15).json()
        
        if "result" in r and "token" in r["result"]:
            cloud_token = r["result"]["token"]
            print("✅ TP-Link OK")
        else:
            print(f"❌ Помилка логіна: {r}")
            raise RuntimeError("TP-Link Login Failed")
            
    except Exception as e:
        print(f"❌ Критична помилка TP-Link: {e}")
        raise

def fetch_device_id():
    global device_id
    print("🔍 Шукаємо розетку...")
    try:
        r = requests.post(
            f"{CLOUD_URL}/?token={cloud_token}",
            json={"method": "getDeviceList"},
            timeout=15
        ).json()
        
        devices = r["result"]["deviceList"]
        print(f"📱 Пристроїв знайдено: {len(devices)}")
        
        for d in devices:
            device_type = d.get("deviceType", "").upper()
            nickname = d.get("nickname", "Unknown")
            print(f"  → {nickname}: {device_type}")
            
            if "PLUG" in device_type:
                device_id = d["deviceId"]
                print(f"✅ ✅ РОЗЕТКА ЗНАЙДЕНА: {nickname} (ID={device_id})")
                return True
        
        print("⚠️ Розеток не знайдено в акаунті")
        return False
        
    except Exception as e:
        print(f"❌ Помилка пошуку пристроїв: {e}")
        return False

def power_present():
    """Перевірка P110: якщо API повертає дані, значить розетка в мережі (світло Є)."""
    if not device_id: return True
    
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
        
        # Якщо є responseData, значить розетка відповіла -> Світло Є
        has_response = bool(r.get("result", {}).get("responseData"))
        
        # Лог для відладки (можна прибрати пізніше)
        # print(f"🔌 P110 Check: {'ONLINE' if has_response else 'OFFLINE'}")
        
        return has_response
        
    except Exception as e:
        print(f"⚠️ P110 помилка запиту (світла немає?): {e}")
        return False

# ================== DTEK PARSER ==================
def build_22_message(text: str):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return None
    
    header = lines[0]
    for line in lines:
        if "2.2" in line and ("Підгрупа" in line or "підгрупу" in line):
            return f"{header}\n\n📍 {line}"
    return None

# ================== TELEGRAM HANDLERS ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def power_job(context: ContextTypes.DEFAULT_TYPE):
    global last_state, power_off_at
    
    state = power_present()
    print(f"⏰ [{kyiv_time()}] Стан світла: {'✅ Є' if state else '❌ НЕМАЄ'}")
    
    if state == last_state:
        return
    
    now = kyiv_time()
    
    if not state:
        # Світло зникло
        power_off_at = time.time()
        msg = f"⚡ Світло зникло — {now}"
        print(f"🚨 АВАРІЯ: {now}")
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
    else:
        # Світло з'явилось
        minutes = int((time.time() - power_off_at) / 60) if power_off_at else 0
        msg = f"🔌 Світло зʼявилось — {now}\n⏱️ Не було: {minutes} хв"
        print(f"✅ ВІДНОВЛЕНО: {now} (був офлайн {minutes} хв)")
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)
    
    last_state = state

# ================== MAIN ==================
def main():
    print("🚀 Ініціалізація системи...")
    
    # 1. Логін в Tapo
    try:
        cloud_login()
        if fetch_device_id():
            print("✅ Розетка успішно підключена")
        else:
            print("⚠️ УВАГА: Працюю без моніторингу розетки (тільки пересилка повідомлень)")
    except Exception as e:
        print(f"❌ Критичний збій TP-Link: {e}")
        # Не падаємо, щоб працював хоча б парсер повідомлень
    
    print("🤖 Запуск Telegram бота...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Обробка повідомлень
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
        handle_message
    ))
    
    # JobQueue для перевірки розетки
    print("⏰ Налаштування JobQueue (інтервал 30с)...")
    if app.job_queue:
        app.job_queue.run_repeating(power_job, interval=30, first=10)
        print("✅ JobQueue запущено")
    else:
        print("❌ ПОМИЛКА: JobQueue не знайдено! Перевір requirements.txt")

    print("🎉 Бот готовий! DTEK 2.2 + P110 Active")
    
    # Запуск Polling
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
