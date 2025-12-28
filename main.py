import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003534080985


def build_22_message(text: str) -> str | None:
    lines = text.splitlines()

    # Шапка: перший непорожній рядок
    header = None
    for line in lines:
        if line.strip():
            header = line
            break
    if header is None:
        return None

    # ===== 1) Формат "Підгрупа 2.2 відключення" (Зміни у графіку) =====
    start_22 = None
    for i, line in enumerate(lines):
        if "Підгрупа" in line and "2.2" in line:
            start_22 = i
            break

    if start_22 is not None:
        # блок 2.2: від заголовка до першої пустої строки
        block = []
        for line in lines[start_22:]:
            if line.strip() == "" and block:
                break
            block.append(line)
        block = [l for l in block if l.strip()]

        # шапка = перші два непорожні рядки
        header_lines = []
        for line in lines:
            if line.strip():
                header_lines.append(line)
            if len(header_lines) == 2:
                break

        result_lines = header_lines + [""] + block
        return "\n".join(result_lines).strip()

    # ===== 2) Формат "О 18:30 / Вмикаємо 2.2 підгрупу" =====
    line_22 = None
    for line in lines:
        if "2.2" in line and "підгрупу" in line:
            line_22 = line
            break

    if line_22:
        if line_22 == header:
            return line_22
        return f"{header}\n{line_22}"

    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    text = msg.text or msg.caption or ""
    if not text:
        return

    payload = build_22_message(text)
    if not payload:
        return

    await context.bot.send_message(chat_id=CHANNEL_ID, text=payload)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
        handle_message,
    ))

    app.run_polling()


if __name__ == "__main__":
    main()
