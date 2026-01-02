import os
import time
import requests
import hmac
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

print("🚀 SvitloBot - DEBUG + FIX switch detection")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003534080985"))
TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET")
TUYA_DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")
TUYA_REGION = "eu"  # перевір: eu/us/cn в https://iot.tuya.com

power_off_start = None

def kyiv_time():
    return datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m %H:%M")

def tuya_api():
    """Повний DEBUG Tuya відповідь"""
    try:
        ts = str(int(time.time() * 1000))  # milliseconds!
        path = f"/v1.0/iot-03/devices/{TUYA_DEVICE_ID}/status"
        
        params = {
            "access_id": TUYA_ACCESS_ID,
            "timestamp": ts
        }
        # CRITICAL FIX: sign = path + params
        sign_str = f"{path}?access_id={TUYA_ACCESS_ID}&timestamp={ts}"
        params["sign"] = hmac.new(TUYA_ACCESS_SECRET.encode(), 
                                 sign_str.encode(), hashlib.sha256).hexdigest()
        
        url = f"https://{TUYA_REGION}.tuya.com{path}"
        
        print(f"🌐 URL: {url}")
        print(f"🔑 Params: access_id={TUYA_ACCESS_ID[:8]}... ts={ts} sign={params['sign'][:8]}...")
        
        resp = requests.get(url, params=params, timeout=10)
        print(f"📊 Status: {resp.status_code}")
        print(f"📄 Response: {resp.text[:400]}")
        
        data = resp.json()
        
        if not data.get("success"):
            print(f"❌ Tuya fail: {data}")
            return None
        
        # DEBUG ВСІ DPS!
        dps = data.get("result", [])
        print("🔍 ALL DPS:")
        for item in dps:
            print(f"  {item['code']}: {item['value']} ({type(item['value'])})")
        
        # Пошук switch (switch_1, switch_led, power_state...)
        for item in dps:
            code = item['code'].lower()
            value = item['value']
            if 'switch' in code or 'power' in code or 'plug' in code:
                is_on = value is True or value == 'true' or value == True or value == 1
                print(f"💡 FOUND {code} = {value} → {'🟢 ON' if is_on else '🔴 OFF'}")
                return is_on
        
        print("⚠️ Switch DPS не знайдено!")
        return False
        
    except Exception as e:
        print(f"💥 Error: {e}")
        return None

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global power_off_start
    
    is_on = tuya_api()
    now = kyiv_time()
    
    if is_on is None:
        msg = "❌ Tuya помилка - перевір логи"
    else:
        if is_on:
            if power_off_start:
                mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - power_off_start).total_seconds() / 60)
                msg = f"🟢 Світло Є! {now}\n⏱ Без світла було: {mins}хв"
                power_off_start = None
            else:
                msg = f"🟢 Світло Є! {now}"
        else:
            if power_off_start is None:
                power_off_start = datetime.now(ZoneInfo("Europe/Kyiv"))
            mins = int((datetime.now(ZoneInfo("Europe/Kyiv")) - power_off_start).total_seconds() / 60)
            msg = f"🔴 Світла нема {mins}хв {now}"
    
    print(f"Sending: {msg}")
    await context.bot.send_message(CHANNEL_ID, msg)
    await context.bot.send_message(update.effective_chat.id, msg)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if '2.2' in text or 'світло' in text:
        await status_cmd(update, context)

def main():
    if not all([BOT_TOKEN, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_DEVICE_ID]):
        print("❌ Set env: BOT_TOKEN, TUYA_*, CHANNEL_ID")
        return
    
    print("✅ START - /status покаже повну Tuya відповідь!")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_msg))
    app.run_polling()

if __name__ == "__main__":
    main()
