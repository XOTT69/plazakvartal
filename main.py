import os
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update
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

TOKEN = None

def tp_link_login():
    global TOKEN
    url = "https://wap.tplinkcloud.com/"
    data = {
        "method": "login",
        "params": {
            "username": TAPO_USERNAME,
            "password": TAPO_PASSWORD
        }
    }
    resp = requests.post(url, json=data, timeout=10).json()
    TOKEN = resp["result"]["token"]
    print("✅ Tapo Cloud авторизовано!")
    return True

def get_device_state():
    if not TOKEN:
        return False
    url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
    data = {"method": "getDeviceState", "params": {"deviceId": DEVICE_ID}}
    try:
        resp = requests.post(url, json=data, timeout=10).json()
        return resp["result"]["device"]["state"]["on"]
    except:
        return None

def power_present():
    """Перевіряє, чи розетка онлайн (220В є)"""
    try:
        state = get_device_state()
        return state is not None
    except:
        return False

def get_status_text():
    if not power_present():
        return "⚡ Світла НЕМА"
    state = get_device_state()
    return "🔌 Світло Є" if state else "🔌 Розетка ВИМК"

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

def build_22_message(text: str) -> str | None:
    lines = text.splitlines()
    header = next((line for line in lines if line.strip()), None)
    if not header:
        return None

    # Підгрупа 2.2
    start_22 = next((i for i, line in enumerate(lines) if "Підгрупа" in line and "2.2" in line), None)
    if start_22 is not None:
        block = [l.strip() for l in lines[start_22:] if l.strip()]
        header_lines = [l.strip() for l in lines if l.strip()][:2]
        return "\n".join(header_lines + [""] + block)

    # Вмикаємо 2.2 підгрупу
    line_22 = next((l for l in lines if "2.2" in l and "підгрупу" in l), None)
    if line_22:
        return line_22 if line_22 == header else f"{header}\n{line_22}"
    return None

# Telegram handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    if not text:
        return
    payload = build_22_message(text)
    if payload:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = get_status_text()
    keyboard = [["📊 Статус"]]
    reply_markup = {"inline_keyboard": keyboard}
    await update.message.reply_text(status, reply_markup=reply_markup)
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status = get_status_text()
    await query.edit_message_text(status)

async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
    data = {"method": "set_device_info", "params": {
        "deviceId": DEVICE_ID,
        "relay_state": 1
    }}
    requests.post(url, json=data, timeout=10)
    status = get_status_text()
    await update.message.reply_text(f"🔌 ВКЛ / {status}")
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://wap.tplinkcloud.com/?token={TOKEN}"
    data = {"method": "set_device_info", "params": {
        "deviceId": DEVICE_ID,
        "relay_state": 0
    }}
    requests.post(url, json=data, timeout=10)
    status = get_status_text()
    await update.message.reply_text(f"🔌 ВИКЛ / {status}")
    await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

def main():
    if not tp_link_login():
        print("❌ Tapo Cloud логін провалився")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🚀 Tapo P110 Cloud Bot запущено!")
    print(f"📱 ID: {DEVICE_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()
