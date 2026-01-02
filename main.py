import os
import requests
import subprocess
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

print("🚀 SvitloBot - FIXED power detect")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TUYA_IP = os.environ.get("TUYA_IP", "178.158.192.123")

outage_start = None

def get_status():
    """FIXED: ping + ports + logic для реального power"""
    try:
        # 1. Ping
        ping_ok = subprocess.call(["ping", "-c1", "-W1", TUYA_IP], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        
        # 2. Port scan типові Tuya: 6666-6668, 80, 443
        ports_open = 0
        ports_to_check = [80, 443, 6666, 6667, 6668]
        for port in ports_to_check:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            if sock.connect_ex((TUYA_IP, port)) == 0:
                ports_open += 1
            sock.close()
        
        # 3. HTTP status
        current = 0.0
        try:
            r = requests.get(f"http://{TUYA_IP}", timeout=1.5)
            if r.status_code == 200:
                current = len(r.text) / 10000.0  # KB normalized
        except:
            pass
        
        # LOGIC: power on якщо ping + ports + activity
        is_on = ping_ok and (ports_open >= 1 or current > 0.01)
        
        print(f"🔍 ping={ping_ok}, ports={ports_open}/{len(ports_to_check)}, "
              f"http={current:.2f}, → 🟢" if is_on else "🔴")
        
        return is_on, current
        
    except Exception as e:
        print(f"❌ {e}")
        return False, 0.0

def format_time_diff(td):
    s = int(td.total_seconds())
    m = s // 60
    s %= 60
    return f"{m}хв {s}с" if m else f"{s}с"

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_on, current = get_status()
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
    
    msg += f"\n📊 {TUYA_IP}"
    await update.message.reply_text(msg)
    
    if CHANNEL_ID:
        await context.bot.send_message(CHANNEL_ID, msg)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if any(word in update.message.text.lower() for word in ['2.2', 'статус']):
        await status_cmd(update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print(f"🌟 FIXED Bot LIVE! {TUYA_IP}")
    app.run_polling()

if __name__ == "__main__":
    import socket  # late import
    main()
