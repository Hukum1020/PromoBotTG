import random
import requests
import os
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters, ConversationHandler

# Переменные из Railway
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
MEDIA_ID = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Лист1'

ASK_PASSWORD = 1

# Загрузка промокодов
def load_promo_codes():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    codes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        code, _, _, used_by = row[0], row[1], row[2], row[3]
        if code and (used_by is None):
            codes.append(code)
    wb.close()
    return codes

# Помечаем промокод как использованный
def mark_code_as_used(code, username):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == code:
            row[3].value = username
            break
    wb.save(EXCEL_FILE)
    wb.close()

# Проверка комментария под постом
def has_user_commented(username):
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        'access_token': ACCESS_TOKEN,
        'fields': 'username,text',
        'limit': 100
    }
    while url:
        response = requests.get(url, params=params)
        data = response.json()
        for comment in data.get('data', []):
            if comment['username'].lower() == username.lower():
                return True
        url = data.get('paging', {}).get('next')
    return False

# Проверка получал ли пользователь промокод
def has_user_received(username):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2):
        if row[3].value and row[3].value.lower() == username.lower():
            wb.close()
            return True
    wb.close()
    return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь свой Instagram-никнейм для проверки!")

# Обработка обычных сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip('@')
    await update.message.reply_text(f"Проверяю комментарий от @{username}…")

    if has_user_received(username):
        await update.message.reply_text("✅ Ты уже получил промокод ранее!")
        return

    if has_user_commented(username):
        promo_codes = load_promo_codes()
        if promo_codes:
            selected_code = random.choice(promo_codes)
            mark_code_as_used(selected_code, username)
            await update.message.reply_text(f"🎁 Вот твой промокод: *{selected_code}*", parse_mode='Markdown')
        else:
            await update.message.reply_text("😔 Промокоды закончились.")
    else:
        await update.message.reply_text("😕 Ты не выполнил условия! Пожалуйста, проверь подписку, лайк и комментарий.")

# Команда /download
async def download_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите пароль для получения файла:")
    return ASK_PASSWORD

# Приём пароля
async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if password == DOWNLOAD_PASSWORD:
        await update.message.reply_document(InputFile(EXCEL_FILE))
    else:
        await update.message.reply_text("❌ Неверный пароль.")
    return ConversationHandler.END

# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Запуск бота
def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    download_conv = ConversationHandler(
        entry_points=[CommandHandler("download", download_start)],
        states={
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(download_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    run_bot()
