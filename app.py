import random
import requests
from openpyxl import load_workbook
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Instagram API settings
ACCESS_TOKEN = 'your_instagram_access_token'
MEDIA_ID = 'your_instagram_post_id'

# Telegram Bot Token
TELEGRAM_TOKEN = 'your_telegram_bot_token'

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Sheet1'  # или другое имя, если ты переименовывала лист

# Загрузка промокодов
def load_promo_codes():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    codes = []
    for row in ws.iter_rows(min_row=2, values_only=True):  # предполагаем, что первая строка — заголовки
        if row[0]:  # если есть код
            codes.append(row[0])
    wb.close()
    return codes

# Удаление использованного кода
def remove_used_code(code):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2):  # предполагаем, что коды в первом столбце
        if row[0].value == code:
            row[0].value = None  # просто стираем использованный код
            break
    wb.save(EXCEL_FILE)
    wb.close()

# Проверка комментариев под постом
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

# Обработка сообщений в Telegram
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip('@')
    await update.message.reply_text(f"Проверяю комментарий от @{username}…")

    if has_user_commented(username):
        promo_codes = load_promo_codes()
        if promo_codes:
            selected_code = random.choice(promo_codes)
            remove_used_code(selected_code)
            await update.message.reply_text(f"🎉 Поздравляем! Ваш промокод: {selected_code}")
        else:
            await update.message.reply_text("😔 Промокоды закончились.")
    else:
        await update.message.reply_text("Комментарий не найден. Убедитесь, что вы прокомментировали нужный пост и повторите попытку.")

# Запуск бота
def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    run_bot()
