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

# Тексты
START_MESSAGE = "Привет! 👋 …"
ASK_USERNAME  = "Пожалуйста, отправь свой Instagram-никнейм…"
FAIL_MESSAGE  = "😕 Ты не выполнил все условия…"
SUCCESS_TEMPLATE = "✅ Вот твой код: *{promo_code}*"
ASK_PASS    = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASS  = "🚫 Неверный пароль."
FILE_MISSING = "🚫 Файл не найден."

# --- Работа с Excel ---
def load_workbook_data():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    data = list(ws.iter_rows(min_row=2, values_only=False))
    wb.close()
    return data

def find_unused_codes():
    rows = load_workbook_data()
    # возвращаем [(код, номер_строки), ...]
    return [
        (r[0].value, r[0].row)
        for r in rows
        if r[0].value and not r[3].value
    ]

def user_already_got(username):
    rows = load_workbook_data()
    return any(r[3].value and r[3].value.lower() == username.lower()
               for r in rows)

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
        # логируем для отладки
        print("Got comments chunk:", resp.get("data", []))
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

# обычный текст (ни ненужный пароль, ни команда)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # если ждём пароль — не трогаем этот хендлер
    if context.user_data.get('awaiting_password'):
        return

    username = update.message.text.strip().lstrip('@')
    # Проверка повторного получения
    if user_already_got(username):
        await update.message.reply_text("🎉 Вы уже получили промокод.")
        return

    await update.message.reply_text(f"Проверяю комментарий @{username}…")
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
        SUCCESS_TEMPLATE.format(promo_code=code),
        parse_mode='Markdown'
    )

# /download — начинаем диалог пароля
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_PASS)
    context.user_data['awaiting_password'] = True

# проверка пароля
async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_password'):
        return  # не в режиме «жду пароль»
    text = update.message.text.strip()
    if text == DOWNLOAD_PASSWORD:
        if os.path.exists(EXCEL_FILE):
            await update.message.reply_document(InputFile(EXCEL_FILE, filename="promo_codes.xlsx"))
        else:
            await update.message.reply_text(FILE_MISSING)
    else:
        await update.message.reply_text(WRONG_PASS)
    # выключаем режим ожидания
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
