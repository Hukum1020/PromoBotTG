import random
import requests
import os
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# Переменные
ACCESS_TOKEN      = os.getenv("ACCESS_TOKEN")
MEDIA_ID          = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Лист1'

# Оригинальные тексты
START_MESSAGE = """Привет! 👋  
Ты на шаг ближе к участию в розыгрыше VIP-билетов на авиашоу «Небо Байсерке – 2025» ✈🎁 Каждый участник получает ПОДАРОК — промокод на скидку 10% на стандартный билет!
Перед тем как выдать тебе промокод, давай проверим, что ты выполнил все условия 👇"""

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

ASK_PASS     = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASS   = "🚫 Неверный пароль. Попробуй ещё раз."
FILE_MISSING = "🚫 Файл не найден."

# --- Работа с Excel ---
def load_workbook_data():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    rows = list(ws.iter_rows(min_row=2, values_only=False))
    wb.close()
    return rows

def find_unused_codes():
    rows = load_workbook_data()
    return [
        (r[0].value, r[0].row)
        for r in rows
        if r[0].value and not r[3].value
    ]

def user_already_got(username):
    rows = load_workbook_data()
    return any(
        r[3].value and r[3].value.lower() == username.lower()
        for r in rows
    )

def mark_code(row, user):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row, column=4, value=user)
    wb.save(EXCEL_FILE)
    wb.close()

# Проверка комментариев
def has_commented(username):
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        'access_token': ACCESS_TOKEN,
        'fields': 'username,text',
        'limit': 100,
    }
    while url:
        resp = requests.get(url, params=params).json()
        for c in resp.get("data", []):
            if c['username'].lower() == username.lower():
                return True
        url = resp.get("paging", {}).get("next")
    return False

# --- Хендлеры ---

# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(START_MESSAGE)
    await update.message.reply_text(ASK_USERNAME)

# выдача промокода
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # если ждём пароль — выходим, это не этот хендлер
    if context.user_data.get('awaiting_password'):
        return

    username = update.message.text.strip().lstrip('@')

    # уже получал?
    if user_already_got(username):
        await update.message.reply_text("🎉 Вы уже получили промокод.")
        return

    await update.message.reply_text(f"Проверяю комментарий от @{username}…")
    if not has_commented(username):
        await update.message.reply_text(FAIL_MESSAGE)
        return

    codes = find_unused_codes()
    if not codes:
        await update.message.reply_text("😔 Промокоды закончились.")
        return

    code, row = random.choice(codes)
    mark_code(row, username)
    await update.message.reply_text(
        SUCCESS_MESSAGE_TEMPLATE.format(promo_code=code),
        parse_mode='Markdown'
    )

# /download → ждем пароль
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_PASS)
    context.user_data['awaiting_password'] = True

# проверка пароля и отправка файла
async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_password'):
        return
    if update.message.text.strip() == DOWNLOAD_PASSWORD:
        if os.path.exists(EXCEL_FILE):
            # отправляем именно .xlsx
            await update.message.reply_document(
                InputFile(EXCEL_FILE, filename="promo_codes.xlsx")
            )
        else:
            await update.message.reply_text(FILE_MISSING)
    else:
        await update.message.reply_text(WRONG_PASS)
    context.user_data['awaiting_password'] = False

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",    start_cmd))
    app.add_handler(CommandHandler("download", download_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_password))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    main()
