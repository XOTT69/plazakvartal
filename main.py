import os
import subprocess
import socket
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

print("🚀 SvitloBot - FINAL socket+ping POWER detect")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TUYA_IP = os.environ.get("TUYA_IP", "178.158.192.123")

outage_start = None

def get_status():
    """FIX socket import + power logic"""
    try:
        # 1. Ping check
        ping_ok = subprocess.call(["ping", "-c1", "-W2", TUYA_IP], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL) == 0
        
        # 2. Tuya port 6668 (MAIN power indicator)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        tuya_port = sock.connect_ex((TUYA_IP, 6668)) == 0
        sock.close()
        
        # 3. HTTP port 80
        http_port = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            http_port = sock.connect_ex((TUYA_IP, 80)) == 0
            sock.close()
        except:
            pass
        
        # POWER LOGIC: Tuya port 6668 = MAIN indicator
        is_on = ping_ok and tuya_port
        ports_open = tuya_port + http_port
        
        print(f"🔍 {TUYA_IP} ping={ping_ok} 6668={tuya_port} 80={http_port} → "
              f"{'🟢' if is_on else '🔴'} ports={ports_open}")
        
        return is_on, ports_open
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0

def format_time_diff(td):
    s = int(td.total_seconds())
    m = s // 60
    s = s % 60
    return f"{m}хв {s}с" if m else f"{s}с"

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_on, ports = get_status()
    now = datetime.now(ZoneInfo("Europe/Kiev"))
    
    global outage_start
    if is_on:
        msg = f"🟢 Світло Є! ⏰ {now.strftime('%d.%m %H:%M')}"
        if outage_start:
            msg += f"\n⏱️ Без світла було: {format_time_diff(now - outage_start)}"
            outage_start = None
    else:
        msg = f"🔴 Світла Немає! ⏰ {now.strftime('%d.%m %H:%M')}"
        outage_start = outage_start or now
        msg += f"\n⏱️ Без світла: {format_time_diff(now - outage_start)}"
    
    msg += f"\n📶 {TUYA_IP} ports={ports}"
    await update.message.reply_text(msg)
    
    if CHANNEL_ID:
        try:
            await context.bot.send_message(CHANNEL_ID, msg)
        except: pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(word in text for word in ['2.2', 'статус', 'світло']):
        await status_cmd(update, context)

def main():
    print(f"🚀 Bot LIVE! Target: {TUYA_IP}:6668")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🌟 READY! /status тест")
    app.run_polling()

if __name__ == "__main__":
    main()
