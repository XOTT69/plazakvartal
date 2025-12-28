import os
import requests
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, 
    MessageHandler, CommandHandler, filters, CallbackQueryHandler
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "-1003534080985"
TAPO_USERNAME = os.getenv("TAPO_USERNAME")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")
DEVICE_ID = "8022215C67F89C63F233A90DF89A9CB424B38E2F"

# Новий API для Tapo
TOKEN = None

def tapo_login():
    """Tapo Cloud логін (нова версія)"""
    global TOKEN
    try:
        # Спочатку логін
        login_url = "https://wap.tplinkcloud.com/tapo/public_app_v2.4.0/user/login"
        login_data = {
            "username": TAPO_USERNAME,
            "password": TAPO_PASSWORD,
            "method": "login"
        }
        resp = requests.post(login_url, json=login_data, timeout=15).json()
        print(f"Login response: {resp}")
        
        if "token" in resp:
            TOKEN = resp["token"]
            print("✅ Tapo Cloud авторизовано!")
            return True
        else:
            print(f"❌ Login failed: {resp}")
            return False
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False

def get_device_info():
    """Отримати статус розетки"""
    if not TOKEN:
        return None
    try:
        url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
        data = {
            "method": "getDeviceList",
            "params": {}
        }
        resp = requests.post(url, json=data, timeout=15).json()
        print(f"Device list response: {resp}")
        
        # Шукаємо нашу розетку
        for device in resp.get("result", {}).get("deviceList", []):
            if device.get("deviceId") == DEVICE_ID:
                state = device.get("basic", {}).get("state", {})
                return {
                    "online": device.get("online"),
                    "relay_state": state.get("relay_state", 0)
                }
        return None
    except Exception as e:
        print(f"❌ Device info error: {e}")
        return None

def power_present():
    """220В є?"""
    info = get_device_info()
    return info is not None and info.get("online")

def get_status_text():
    info = get_device_info()
    if not info:
        return "❌ Розетка офлайн"
    if not info.get("online"):
        return "⚡ Світла НЕМА (офлайн)"
    return "🔌 Світло Є" if info.get("relay_state") else "🔌 Розетка ВИМК"

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def build_22_message(text: str) -> str | None:
    lines = text.splitlines()
    header = next((l.strip() for l in lines if l.strip()), None)
    if not header:
        return None
    
    # Підгрупа 2.2
    for i, line in enumerate(lines):
        if "Підгрупа" in line and "2.2" in line:
            block = [l.strip() for l in lines[i:] if l.strip()]
            return "\n".join([header] + [""] + block)
    
    # 2.2 підгрупу
    for line in lines:
        if "2.2" in line and "підгрупу" in line:
            return f"{header}\n{line.strip()}"
    return None

# Telegram handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = get_status_text()
    keyboard = [[InlineKeyboardButton("📊 Статус", callback_data="status")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(status, reply_markup=reply_markup)
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status = get_status_text()
    await query.edit_message_text(status)

async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_device_info()
    if info and info.get("online"):
        url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
        data = {"method": "set_device_info", "params": {
            "deviceId": DEVICE_ID, "relay_state": 1
        }}
        requests.post(url, json=data, timeout=10)
    status = get_status_text()
    await update.message.reply_text(f"🔌 ВКЛ / {status}")
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_device_info()
    if info and info.get("online"):
        url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
        data = {"method": "set_device_info", "params": {
            "deviceId": DEVICE_ID, "relay_state": 0
        }}
        requests.post(url, json=data, timeout=10)
    status = get_status_text()
    await update.message.reply_text(f"🔌 ВИКЛ / {status}")
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

def main():
    print("🔄 Спроба підключення до Tapo Cloud...")
    if not tapo_login():
        print("❌ Не вдалось авторизуватись в Tapo Cloud")
        print("Перевір: email, пароль, DEVICE_ID")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🚀 Tapo P110 Cloud Bot запущено!")
    print(f"📱 Device ID: {DEVICE_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()
