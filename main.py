import os
import time
import tinytuya
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

print("🚀 SvitloBot - tinytuya FINAL tinytuya==1.8.5 OK")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")  # bfa671762a871e5405rvq4
TUYA_IP = os.environ.get("TUYA_IP", "178.158.192.123")
TUYA_LOCAL_KEY = os.environ.get("TUYA_LOCAL_KEY", "")  

if not all([BOT_TOKEN, TUYA_DEVICE_ID, TUYA_IP]):
    print("❌ ENV: BOT_TOKEN, TUYA_DEVICE_ID, TUYA_IP обов'язкові!")
    exit(1)

# Tinytuya device
device = tinytuya.OutletDevice(TUYA_DEVICE_ID, TUYA_IP, TUYA_LOCAL_KEY)
device.set_version(3.3)
device.set_socketPersistent(True)

last_power_on = None
outage_start = None

def get_status():
    try:
        print("🔍 tinytuya.status()...")
        data = device.status()
        print(f"📊 DPS: {data}")
        
        dps = data.get('dps', {})
        switch_key = None
        for key in ['switch_1', 'switch', 'plug_1', 'power', 'plug_switch']:
            if key in dps:
                switch_key = key
                break
        
        if switch_key:
            is_on = dps[switch_key]
            current = dps.get('current', dps.get('ampere', 0))
            print(f"💡 {switch_key}: {is_on} (current: {current})")
            return bool(is_on), float(current or 0)
        
        print("❌ DPS не знайдено: ", list(dps.keys()))
        return False, 0
        
    except Exception as e:
        print(f"❌ tinytuya ERROR: {e}")
        # Fallback ping
        try:
            device.ping()
            print("✅ Device ping OK")
        except:
            print("❌ Device offline")
        return False, 0

def format_time_diff(td):
    total_sec = int(td.total_seconds())
    mins = total_sec // 60
    secs = total_sec % 60
    if mins == 0: return f"{secs}с"
    return f"{mins}хв {secs}с"

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_on, current = get_status()
    now = datetime.now(ZoneInfo("Europe/Kiev"))
    
    global outage_start
    
    if is_on:
        msg = f"🟢 Світло Є! ⏰ {now.strftime('%d.%m %H:%M')}"
        if outage_start:
            duration = now - outage_start
            msg += f"\n⏱️ Без світла було: {format_time_diff(duration)}"
            outage_start = None
    else:
        msg = f"🔴 Світла Немає! ⏰ {now.strftime('%d.%m %H:%M')}"
        outage_start = outage_start or now
        if outage_start:
            duration = now - outage_start
            msg += f"\n⏱️ Без світла: {format_time_diff(duration)}"
    
    msg += f"\n⚡ Струм: {current:.2f}A"
    
    await update.message.reply_text(msg)
    
    # Канал
    if CHANNEL_ID:
        try:
            await context.bot.send_message(CHANNEL_ID, msg)
        except Exception as e:
            print(f"❌ Channel error: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(word in text for word in ['2.2', 'статус', 'світло', 'status']):
        await status_cmd(update, context)

def monitor_power(context: ContextTypes.DEFAULT_TYPE):
    """30s check → канал якщо зміна"""
    global outage_start
    is_on, _ = get_status()
    now = datetime.now(ZoneInfo("Europe/Kiev"))
    
    changed = False
    if is_on and outage_start:
        duration = now - outage_start
        msg = f"🟢 Світло Є! ⏰ {now.strftime('%d.%m %H:%M')}\n⏱️ Без світла було: {format_time_diff(duration)}"
        context.bot.send_message(CHANNEL_ID, msg)
        outage_start = None
        changed = True
    elif not is_on and outage_start is None:
        outage_start = now
        changed = True
    
    if changed:
        print(f"📢 Channel update: {'🟢' if is_on else '🔴'}")

def main():
    print("✅ tinytuya imported OK")
    print(f"📍 Device: {TUYA_DEVICE_ID}@{TUYA_IP}")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    app.job_queue.run_repeating(monitor_power, interval=30, first=5)
    
    print("🌟 Bot + tinytuya LIVE! Тест /status")
    app.run_polling()

if __name__ == "__main__":
    main()
