import os
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

print("🚀 SvitloBot - tinytuya BYPASS (requests ONLY)")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID", "bfa671762a871e5405rvq4")
TUYA_IP = os.environ.get("TUYA_IP", "178.158.192.123")

outage_start = None

def get_status():
    """Power meter via HTTP (якщо розетка має web UI) або ping + logic"""
    try:
        # Ping розетки
        response = os.system(f"ping -c1 -W1 {TUYA_IP} > /dev/null 2>&1")
        is_online = response == 0
        
        # HTTP probe на типові Tuya порти (80/web)
        try:
            r = requests.get(f"http://{TUYA_IP}", timeout=2)
            current = len(r.content)/1000 if r.status_code == 200 else 0.0
        except:
            current = 0.0
        
        is_on = is_online and current > 0.1
        print(f"📡 {TUYA_IP} ping={is_online}, http={current:.1f}KB → on={is_on}")
        return is_on, current
    except Exception as e:
        print(f"❌ Probe: {e}")
        return False, 0.0

def format_time_diff(td):
    s = int(td.total_seconds())
    m, s = divmod(s, 60)
    return f"{m}хв {s}с" if m else f"{s}с"

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_on, current = get_status()
    now = datetime.now(ZoneInfo("Europe/Kiev"))
    
    global outage_start
    if is_on:
        msg = f"🟢 Світло Є! ⏰ {now.strftime('%d.%m %H:%M')}"
        if outage_start:
            msg += f"\n⏱️ Без світла було: {format_time_diff(now-outage_start)}"
            outage_start = None
    else:
        msg = f"🔴 Немає! ⏰ {now.strftime('%d.%m %H:%M')}"
        outage_start = outage_start or now
        msg += f"\n⏱️ Без світла: {format_time_diff(now-outage_start)}"
    
    msg += f"\n🌐 {TUYA_IP}"
    await update.message.reply_text(msg)
    
    if CHANNEL_ID:
        try:
            await context.bot.send_message(CHANNEL_ID, msg)
        except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if '2.2' in text or 'статус' in text:
        await status_cmd(update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"🌟 Bot LIVE! IP: {TUYA_IP}")
    app.run_polling()

if __name__ == "__main__":
    main()
