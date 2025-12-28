import os
import asyncio
from kasa import SmartPlug
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "-1003534080985"
TAPO_USERNAME = os.getenv("TAPO_USERNAME")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")

plug = None

async def init_plug():
    global plug
    try:
        plug = SmartPlug("tapo_p110")
        await plug.protocol.initiate_connection()
        await plug.update()
        print("✅ python-kasa P110 підключено!")
    except Exception as e:
        print(f"❌ kasa error: {e}")

def build_22_message(text: str) -> str | None:
    lines = text.splitlines()
    header = next((l.strip() for l in lines if l.strip()), None)
    if not header:
        return None
    for i, line in enumerate(lines):
        if "Підгрупа" in line and "2.2" in line:
            block = [l.strip() for l in lines[i:] if l.strip()]
            return "\n".join([header] + [""] + block)
    for line in lines:
        if "2.2" in line and "підгрупу" in line:
            return f"{header}\n{line.strip()}"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    payload = build_22_message(text)
    if payload:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if plug:
        await plug.update()
        status = "🔌 Світло Є" if plug.is_on else "⚡ Світла НЕМА"
        await update.message.reply_text(status)
        await context.bot.send_message(chat_id=CHANNEL_ID, text=status)
    else:
        await update.message.reply_text("❌ Розетка недоступна")

async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if plug:
        await plug.turn_on()
        await plug.update()
        status = "🔌 Світло Є" if plug.is_on else "⚡ Світла НЕМА"
        await update.message.reply_text(f"🔌 ВКЛ / {status}")
        await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if plug:
        await plug.turn_off()
        await plug.update()
        status = "🔌 Світло Є" if plug.is_on else "⚡ Світла НЕМА"
        await update.message.reply_text(f"🔌 ВИКЛ / {status}")
        await context.bot.send_message(chat_id=CHANNEL_ID, text=status)

async def main():
    await init_plug()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    
    print("🚀 Railway python-kasa Bot запущено!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
