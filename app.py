import random
import os
import requests
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# Переменные окружения (заданы в Railway)
ACCESS_TOKEN      = os.getenv("ACCESS_TOKEN")
MEDIA_ID          = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Лист1'

# Тексты ответов
ASK_USERNAME = "Пожалуйста, отправь свой Instagram-никнейм (например, @yourname)"
SUCCESS_MESSAGE_TEMPLATE = "🎁 Твой персональный промокод: *{promo_code}*"
ALREADY_MESSAGE = "🎉 Вы уже получили промокод."
NO_CODES_MESSAGE = "😔 Промокоды закончились."
FAIL_MESSAGE = ("😕 Ты не выполнил все условия.\n"
                "Проверь, пожалуйста:\n"
                "1. Подписан ли ты на @aviashow.kz\n"
                "2. Лайкнул ли пост с розыгрышем\n"
                "3. Отметил 2 друзей в комментарии под постом\n\n"
                "🔁 Когда всё будет готово — отправь ник ещё раз.")
ASK_PASS     = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASS   = "🚫 Неверный пароль. Попробуй ещё раз."
FILE_MISSING = "🚫 Файл не найден."

# --- Работа с Excel-файлом ---

def load_rows():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    rows = list(ws.iter_rows(min_row=2, values_only=False))
    wb.close()
    return rows

def user_already_got(username: str) -> bool:
    for row in load_rows():
        used = row[3].value  # столбец D — Used
        if used and used.lower() == username.lower():
            return True
    return False

def get_unused_codes():
    free = []
    for row in load_rows():
        code = row[0].value
        used = row[3].value
        if code and not used:
            free.append((code, row[0].row))
    return free

def mark_code_as_used(row_number: int, username: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row_number, column=4, value=username)
    wb.save(EXCEL_FILE)
    wb.close()

# --- Проверка комментариев в Instagram ---

def has_user_commented(username: str) -> bool:
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        'access_token': ACCESS_TOKEN,
        'fields': 'username,text',
        'limit': 100
    }
    while url:
        resp = requests.get(url, params=params).json()
        for c in resp.get('data', []):
            if c.get('username', '').lower() == username.lower():
                return True
        url = resp.get('paging', {}).get('next')
    return False

# --- Хендлеры Telegram ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # если бот ждёт пароль — пропускаем
    if context.user_data.get('awaiting_password'):
        return

    # считаем, что это никнейм
    username = text.lstrip('@')

    # 1) проверка: уже получал?
    if user_already_got(username):
        await update.message.reply_text(ALREADY_MESSAGE)
        return

    # 2) проверка комментария
    await update.message.reply_text(f"🔍 Проверяю комментарий от @{username}…")
    if not has_user_commented(username):
        await update.message.reply_text(FAIL_MESSAGE)
        return

    # 3) выдача промокода
    free = get_unused_codes()
    if not free:
        await update.message.reply_text(NO_CODES_MESSAGE)
        return

    code, row = random.choice(free)
    mark_code_as_used(row, username)
    await update.message.reply_text(
        SUCCESS_MESSAGE_TEMPLATE.format(promo_code=code),
        parse_mode='Markdown'
    )

# Обработка /download
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_PASS)
    context.user_data['awaiting_password'] = True

# Проверка пароля и отправка файла
async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_password'):
        return
    if update.message.text.strip() == DOWNLOAD_PASSWORD:
        if os.path.exists(EXCEL_FILE):
            # Отправляем файл как .xlsx
            with open(EXCEL_FILE, 'rb') as f:
                await update.message.reply_document(
                    InputFile(f, filename="promo_codes.xlsx")
                )
        else:
            await update.message.reply_text(FILE_MISSING)
    else:
        await update.message.reply_text(WRONG_PASS)
    context.user_data['awaiting_password'] = False

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("download", download_cmd))
    # сначала проверяем пароль
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_password))
    # потом — все остальные тексты
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    main()
