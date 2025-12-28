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

print("🚀 === SVITLOBOT НОВИЙ ===")

# CONFIG
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TAPO_EMAIL = os.environ["TAPO_USERNAME"]
TAPO_PASSWORD = os.environ["TAPO_PASSWORD"]
CLOUD_URL = "https://eu-wap.tplinkcloud.com"

cloud_token = None
device_id = None
last_state = None
power_off_at = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def cloud_login():
    global cloud_token
    print("🔌 TP-Link логін...")
    r = requests.post(CLOUD_URL, json={
        "method": "login",
        "params": {
            "appType": "Tapo_Android",
            "cloudUserName": TAPO_EMAIL,
            "cloudPassword": TAPO_PASSWORD,
            "terminalUUID": "svitlobot"
        }
    }, timeout=15).json()
    cloud_token = r["result"]["token"]
    print("✅ TP-Link OK")

def fetch_device_id():
    global device_id
    print("🔍 Шукаємо розетку...")
    r = requests.post(f"{CLOUD_URL}/?token={cloud_token}", json={"method": "getDeviceList"}, timeout=15).json()
    devices = r["result"]["deviceList"]
    
    print(f"📱 Пристроїв: {len(devices)}")
    for d in devices:
        device_type = d.get("deviceType", "").upper()
        nickname = d.get("nickname", "Unknown")
        print(f"  → {nickname}: {device_type}")
        
        if "PLUG" in device_type:
            device_id = d["deviceId"]
            print(f"✅ ✅ РОЗЕТКА: {nickname}")
            return True
    
    print("⚠️ Розеток не знайдено")
    return False

def power_present():
    """P110: responseData Є = світло Є"""
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
        
        has_response = bool(r["result"].get("responseData"))
        print(f"🔌 P110: {'ONLINE' if has_response else 'OFFLINE'}")
        return has_response
        
    except Exception as e:
        print(f"⚠️ P110 помилка: {e}")
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
    print(f"⏰ [{kyiv_time()}] Світло: {'✅' if state else '❌'}")
    
    if state == last_state:
        return
    
    now = kyiv_time()
    if not state:
        power_off_at = time.time()
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚡ Світло зникло — {now}")
        print(f"🚨 АВАРІЯ: {now}")
    else:
        minutes = int((time.time() - power_off_at) / 60) if power_off_at else 0
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"🔌 Світло зʼявилось — {now}\n⏱️ Не було: {minutes} хв")
        print(f"✅ ВІДНОВЛЕНО: {now}")
    
    last_state = state

def main():
    print("🚀 Ініціалізація...")
    cloud_login()
    tplink_ok = fetch_device_id()
    print(f"🔌 TP-Link: {'✅ OK' if tplink_ok else '⚠️ SKIP'}")
    
    print("🤖 Telegram бот...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(power_job, interval=30, first=10)
    
    print("🎉 DTEK 2.2 + P110 АКТИВНІ!")
    print("⏰ Перевірка кожні 30 секунд")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
