import random
import requests
import os
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# Переменные окружения
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
MEDIA_ID = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Лист1'

# Сообщения
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

ALREADY_RECEIVED_MESSAGE_TEMPLATE = """✅ Вы уже получили промокод ранее:
🎁 Ваш персональный промокод: *{promo_code}*

💡 Используйте его на [ticketon.kz](https://ticketon.kz) при покупке стандартного билета.
"""

FAIL_MESSAGE = """😕 Ты не выполнил все условия.  
Проверь, пожалуйста:
1. Подписан ли ты на @aviashow.kz  
2. Лайкнул ли пост с розыгрышем  
3. Отметил 2 друзей в комментарии под постом

🔁 Когда всё будет готово — просто отправь мне свой ник снова. Я проверю ещё раз!
"""

ASK_PASSWORD_MESSAGE = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASSWORD_MESSAGE = "🚫 Неверный пароль. Попробуйте снова."
FILE_NOT_FOUND_MESSAGE = "🚫 Файл не найден."

# Работа с промокодами
def load_promo_codes():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    codes = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        code_cell, used_cell = row[0], row[3]
        if code_cell.value and (used_cell.value is None or used_cell.value == ''):
            codes.append((code_cell.value, used_cell.row))
    wb.close()
    return codes

def find_existing_code(username):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2, values_only=False):
        code_cell, used_cell = row[0], row[3]
        if used_cell.value and used_cell.value.lower() == username.lower():
            code_value = code_cell.value
            wb.close()
            return code_value
    wb.close()
    return None

def mark_code_as_used(row_number, username):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row_number, column=4, value=username)
    wb.save(EXCEL_FILE)
    wb.close()

# Проверка комментария в Instagram
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

# Команда /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_MESSAGE)
    await update.message.reply_text(ASK_USERNAME)
    context.user_data["started"] = True

# Команда /download
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_PASSWORD_MESSAGE)
    context.user_data['awaiting_password'] = True

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if context.user_data.get('awaiting_password'):
        if text == DOWNLOAD_PASSWORD:
            if os.path.exists(EXCEL_FILE):
                with open(EXCEL_FILE, 'rb') as file:
                    await update.message.reply_document(InputFile(file, filename="promo_codes.xlsx"))
            else:
                await update.message.reply_text(FILE_NOT_FOUND_MESSAGE)
        else:
            await update.message.reply_text(WRONG_PASSWORD_MESSAGE)
        context.user_data['awaiting_password'] = False
        return

    if not context.user_data.get("started"):
        await start_command(update, context)
        return

    username = text.lstrip('@')
    await update.message.reply_text(f"Проверяю комментарий от @{username}…")

    if has_user_commented(username):
        existing_code = find_existing_code(username)
        if existing_code:
            await update.message.reply_text(
                ALREADY_RECEIVED_MESSAGE_TEMPLATE.format(promo_code=existing_code),
                parse_mode='Markdown'
            )
        else:
            promo_codes = load_promo_codes()
            if promo_codes:
                selected_code, row_number = random.choice(promo_codes)
                mark_code_as_used(row_number, username)
                await update.message.reply_text(
                    SUCCESS_MESSAGE_TEMPLATE.format(promo_code=selected_code),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("😔 Промокоды закончились.")
    else:
        await update.message.reply_text(FAIL_MESSAGE)

# Запуск бота
def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == '__main__':
    run_bot()
