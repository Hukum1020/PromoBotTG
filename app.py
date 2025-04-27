import os
import random
import logging
import requests
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настроим логирование
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные из окружения
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
MEDIA_ID = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = "promo_codes_test.xlsx"
SHEET_NAME = "Лист1"

# Тексты сообщений
START_MESSAGE = """Привет! 👋  
Ты на шаг ближе к участию в розыгрыше VIP-билетов на авиашоу «Небо Байсерке – 2025» ✈🎁 Каждый участник получает ПОДАРОК — промокод на скидку 10% на стандартный билет!
Перед тем как выдать тебе промокод, давай проверим, что ты выполнил все условия 👇
"""

ASK_USERNAME = "Пожалуйста, отправь свой Instagram-никнейм (например, @yourname)"

SUCCESS_MESSAGE_TEMPLATE = """✅ Отлично, все условия выполнены:
• Подписка на @aviashow.kz  
• Лайк на пост с розыгрышем  
• Комментарий с отметкой двух друзей
🎁 Вот твой персональный промокод: *{promo_code}*
💡 Используй его на [ticketon.kz](https://ticketon.kz) при покупке стандартного билета и получи скидку:
- до 31 мая — 3000 ₸  
- с 1 июня по 31 июля — 4000 ₸  
- с 1 по 17 августа — 5000 ₸
Спасибо за участие и удачи в розыгрыше! Итоги — 1 июня!
"""

FAIL_MESSAGE = """😕 Ты не выполнил все условия.  
Проверь, пожалуйста:
1. Подписан ли ты на @aviashow.kz  
2. Лайкнул ли пост с розыгрышем  
3. Отметил 2 друзей в комментарии под постом
🔁 Когда всё будет готово — просто отправь мне свой ник снова. Я проверю ещё раз!
"""

WINNER_MESSAGE = """🎉 Поздравляем! Ты выиграл VIP-билет на авиашоу «Небо Байсерке – 2025»!
Наш менеджер скоро свяжется с тобой, чтобы выслать билет.  
Следи за новостями в сторис и до встречи 17 августа на аэродроме Байсерке!
"""

ASK_PASSWORD_MESSAGE = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASSWORD_MESSAGE = "🚫 Неверный пароль. Попробуйте снова."
FILE_NOT_FOUND_MESSAGE = "🚫 Файл не найден."

# --- Работа с таблицей промокодов ---

def load_promo_codes():
    """Возвращает список (код, номер строки) свободных промокодов."""
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    free = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        code_cell, used_cell = row[0], row[3]
        if code_cell.value and not used_cell.value:
            free.append((code_cell.value, code_cell.row))
    wb.close()
    return free

def find_user_row(username: str):
    """
    Ищет, есть ли уже username в колонке USED.
    Если да — возвращает True.
    """
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2, values_only=False):
        used_cell = row[3]
        if used_cell.value and used_cell.value.lower() == username.lower():
            wb.close()
            return True
    wb.close()
    return False

def mark_code_as_used(row_number: int, username: str):
    """Помечает строку row_number записью username."""
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row_number, column=4, value=username)
    wb.save(EXCEL_FILE)
    wb.close()

# --- Проверка комментариев в Instagram ---

def fetch_comments():
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "username,text",
        "limit": 100,
    }
    all_users = []
    while url:
        resp = requests.get(url, params=params)
        data = resp.json()
        for c in data.get("data", []):
            all_users.append(c["username"].lower())
        url = data.get("paging", {}).get("next")
    logger.info(f"🛠 Debug — все найденные юзеры в комментариях: {all_users}")
    return all_users

# --- Хендлеры Telegram ---

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # проверка на режим скачивания
    if context.user_data.get("awaiting_password"):
        context.user_data["awaiting_password"] = False
        if text == DOWNLOAD_PASSWORD:
            if os.path.exists(EXCEL_FILE):
                await update.message.reply_document(InputFile(EXCEL_FILE, filename="promo_codes.xlsx"))
            else:
                await update.message.reply_text(FILE_NOT_FOUND_MESSAGE)
        else:
            await update.message.reply_text(WRONG_PASSWORD_MESSAGE)
        return

    # если команда /download
    if text.lower() == "/download":
        context.user_data["awaiting_password"] = True
        await update.message.reply_text(ASK_PASSWORD_MESSAGE)
        return

    # иначе — это никнейм для выдачи промокода
    username = text.lstrip("@").lower()
    await update.message.reply_text(f"🔍 Проверяю комментарий от @{username}…")
    commenters = fetch_comments()

    if username not in commenters:
        await update.message.reply_text(FAIL_MESSAGE)
        return

    # уже получал?
    if find_user_row(username):
        await update.message.reply_text("ℹ️ Вы уже получили промокод.")
        return

    # раздаем новый
    free_codes = load_promo_codes()
    if not free_codes:
        await update.message.reply_text("😔 Промокоды закончились.")
        return

    code, row = random.choice(free_codes)
    mark_code_as_used(row, username)
    await update.message.reply_text(
        SUCCESS_MESSAGE_TEMPLATE.format(promo_code=code),
        parse_mode="Markdown",
    )

# --- Запуск бота ---

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
