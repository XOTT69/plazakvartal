import os
import re
from datetime import timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003534080985


def format_duration(start_str: str, end_str: str) -> str:
    """Рахує та форматує тривалість проміжку як '(X.X год)' з хвилинами."""
    try:
        start_h, start_m = map(int, start_str.split(':'))
        end_h, end_m = map(int, end_str.split(':'))
        start = timedelta(hours=start_h, minutes=start_m)
        end = timedelta(hours=end_h, minutes=end_m)
        duration = end - start
        if duration.total_seconds() <= 0:
            return ""
        hours = duration.total_seconds() / 3600
        return f"({hours:.1f} год)"
    except ValueError:
        return ""


def parse_dark_hours(text: str) -> tuple[str, str]:
    """Парсить проміжки, замінює в тексті на +дужки і рахує загальну тривалість."""
    patterns = [
        r'(\d{2}:\d{2})[\s–-](\d{2}:\d{2})',
        r'від\s+(\d{2}:\d{2})\s+до\s+(\d{2}:\d{2})',
        r'з\s+(\d{2}:\d{2})\s+до\s+(\d{2}:\d{2})',
    ]
    total_minutes = 0
    modified_text = text
    
    for pattern in patterns:
        matches = list(re.finditer(pattern, modified_text, re.IGNORECASE))
        for match in reversed(matches):  # Зворотний порядок
            groups = match.groups()
            if len(groups) == 2:
                start_str, end_str = groups
                duration_str = format_duration(start_str, end_str)
                if duration_str:
                    # Видаляємо оригінальний пробіл/розділювач перед заміною
                    prefix = "–" if "–" in match.group(0) else "-"
                    replacement = f"{start_str}{prefix}{end_str}{duration_str}"
                    modified_text = (modified_text[:match.start()] + 
                                   replacement + 
                                   modified_text[match.end():])
                    # Додаємо до загальної тривалості
                    start_h, start_m = map(int, start_str.split(':'))
                    end_h, end_m = map(int, end_str.split(':'))
                    dur_td = timedelta(hours=end_h - start_h, minutes=end_m - start_m)
                    total_minutes += dur_td.total_seconds() / 60
    
    hours = total_minutes / 60
    summary = f"⚫ Без світла: {hours:.1f} годин" if hours > 0 else ""
    return modified_text, summary


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
        block_text = "\n".join([l for l in block if l.strip()])

        # шапка = перші два непорожні рядки
        header_lines = []
        for line in lines:
            if line.strip():
                header_lines.append(line)
            if len(header_lines) == 2:
                break

        full_text = "\n".join(header_lines + [""] + [block_text]).strip()
        
        # Парсимо та додаємо дужки + підсумок
        parsed_text, dark_info = parse_dark_hours(full_text)
        if dark_info:
            parsed_text += f"\n\n{dark_info}"
        return parsed_text

    # ===== 2) Формат "О 18:30 / Вмикаємо 2.2 підгрупу" =====
    line_22 = None
    for line in lines:
        if "2.2" in line and "підгрупу" in line:
            line_22 = line
            break

    if line_22:
        full_text = line_22 if line_22 == header else f"{header}\n{line_22}"
        parsed_text, dark_info = parse_dark_hours(full_text)
        if dark_info:
            parsed_text += f"\n\n{dark_info}"
        return parsed_text

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
