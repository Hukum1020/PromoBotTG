import random
import requests
import os
from openpyxl import load_workbook
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Переменные окружения
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
MEDIA_ID = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

EXCEL_FILE = 'promo_codes_test.xlsx'
SHEET_NAME = 'Sheet1'

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

FAIL_MESSAGE = """😕 Ты не выполнил все условия.  
Проверь, пожалуйста:
1. Подписан ли ты на @aviashow.kz  
2. Лайкнул ли пост с розыгрышем  
3. Отметил 2 друзей в комментарии под постом

🔁 Когда всё будет готово — просто отправь мне свой ник снова. Я проверю ещё раз!
"""

# Загрузка свободных промокодов
def load_promo_codes():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    codes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        code, status = row[0], row[1]
        if code and (status is None or str(status).lower() != "used"):
            codes.append(code)
    wb.close()
    return codes

# Пометка промокода как использованного
def mark_code_as_used(code):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == code:
            row[1].value = "used"
            break
    wb.save(EXCEL_FILE)
    wb.close()

# Проверка комментария пользователя в Instagram
def has_user_commented(username):
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        'access_token': ACCESS_TOKEN,
        'fields': 'username,text',
        'limit': 100
    }
    while url:
        try:
            print(f"[INFO] Запрос к Instagram API: {url}")
            response = requests.get(url, params=params)
            print(f"[INFO] Ответ: {response.status_code} | {response.text}")
            data = response.json()

            for comment in data.get('data', []):
                if comment['username'].lower() == username.lower():
                    print(f"[INFO] Комментарий найден от @{username}")
                    return True

            url = data.get('paging', {}).get('next')
        except Exception as e:
            print(f"[ERROR] Ошибка при обращении к Instagram API: {e}")
            return False
    return False

# Обработка Telegram-сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("started"):
        await update.message.reply_text(START_MESSAGE)
        await update.message.reply_text(ASK_USERNAME)
        context.user_data["started"] = True
        return

    username = update.message.text.strip().lstrip('@')
    await update.message.reply_text(f"Проверяю комментарий от @{username}…")

    if has_user_commented(username):
        promo_codes = load_promo_codes()
        if promo_codes:
            selected_code = random.choice(promo_codes)
            mark_code_as_used(selected_code)
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("[INFO] Бот запущен.")
    print("ACCESS_TOKEN:", ACCESS_TOKEN)
    print("MEDIA_ID:", MEDIA_ID)

    app.run_polling()

if __name__ == '__main__':
    run_bot()
