import os
import random
import json
import logging
import requests
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логирования
def setup_logging():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
    )

# Переменные окружения
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")         # Page Access Token
MEDIA_ID           = os.getenv("MEDIA_ID")             # Instagram Business Account ID
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")       # Telegram Bot Token
DOWNLOAD_PASSWORD  = os.getenv("DOWNLOAD_PASSWORD")    # Пароль для /download
CREDENTIALS_JSON   = os.getenv("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID     = os.getenv("SHEET_ID")             # ID Google Sheet

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

Спасибо за участие и удачи в розыгрыше! Итоги — 1 июня!"""

FAIL_MESSAGE = """😕 Ты не выполнил все условия.  
Проверь, пожалуйста:
1. Подписан ли ты на @aviashow.kz  
2. Лайк на пост с розыгрышем  
3. Отметил 2 друзей в комментарии под постом

🔁 Когда всё будет готово — просто отправь мне свой ник снова. Я проверю ещё раз!"""

WINNER_MESSAGE = """🎉 Поздравляем! Ты выиграл VIP-билет на авиашоу «Небо Байсерке – 2025»!
Наш менеджер скоро свяжется с тобой, чтобы выслать билет.  
Следи за новостями в сторис и до встречи 17 августа на аэродроме Байсерке!"""

ASK_PASS     = "Пожалуйста, отправьте пароль для скачивания файла."
WRONG_PASS   = "🚫 Неверный пароль. Попробуйте снова."
FILE_MISSING = "🚫 Файл не найден."

# Инициализация Google Sheets с обработкой CREDENTIALS_JSON
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

def init_sheet():
    try:
        creds_dict = json.loads(CREDENTIALS_JSON)
        # Восстанавливаем корректные переносы строк в ключе
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n").strip()
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        return sheet
    except Exception as e:
        raise ValueError(f"❌ Ошибка подключения к Google Sheets: {e}")

# Загрузка и обновление промокодов

def load_promo_codes(sheet):
    all_values = sheet.get_all_values()
    free = []
    given = {}
    for idx, row in enumerate(all_values[1:], start=2):
        code = row[0].strip()
        used = row[3].strip() if len(row) > 3 else ""
        if used:
            given[used.lower()] = code
        else:
            free.append((code, idx))
    return free, given

def mark_code_as_used(sheet, row_idx, username):
    sheet.update_cell(row_idx, 4, username)

# Проверка комментариев в Instagram

def has_user_commented(username):
    url = f"https://graph.facebook.com/v22.0/{MEDIA_ID}/comments"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "username,text",
        "limit": 100,
    }
    commenters = []
    while url:
        resp = requests.get(url, params=params).json()
        for c in resp.get("data", []):
            commenters.append(c.get("username", "").lower())
        url = resp.get("paging", {}).get("next")
    logging.info(f"🛠 Debug — все найденные юзеры: {commenters}")
    return username.lower() in commenters

# Обработчики Telegram

def register_handlers(app, sheet):
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        # Парольный режим
        if context.user_data.get("awaiting_password"):
            context.user_data["awaiting_password"] = False
            if text == DOWNLOAD_PASSWORD:
                # экспорт Google Sheet в xlsx
                download_url = (
                    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
                )
                token = sheet.client.auth.access_token
                headers = {"Authorization": f"Bearer {token}"}
                r = requests.get(download_url, headers=headers)
                if r.status_code == 200:
                    await update.message.reply_document(
                        document=r.content,
                        filename="promo_codes.xlsx"
                    )
                else:
                    await update.message.reply_text(FILE_MISSING)
            else:
                await update.message.reply_text(WRONG_PASS)
            return

        # Команда /download
        if text.lower() == "/download":
            context.user_data["awaiting_password"] = True
            await update.message.reply_text(ASK_PASS)
            return

        # Обработка никнейма
        username = text.lstrip("@").lower()
        await update.message.reply_text(START_MESSAGE)
        await update.message.reply_text(ASK_USERNAME)

        free, given = load_promo_codes(sheet)
        if username in given:
            await update.message.reply_text(
                WINNER_MESSAGE if False else
                SUCCESS_MESSAGE_TEMPLATE.format(promo_code=given[username]),
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(f"🔍 Проверяю комментарий от @{username}…")
        if not has_user_commented(username):
            await update.message.reply_text(FAIL_MESSAGE)
            return

        if not free:
            await update.message.reply_text("😔 Промокоды закончились.")
            return
        code, row = random.choice(free)
        mark_code_as_used(sheet, row, username)
        await update.message.reply_text(
            SUCCESS_MESSAGE_TEMPLATE.format(promo_code=code),
            parse_mode="Markdown"
        )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Запуск бота

def main():
    setup_logging()
    sheet = init_sheet()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app, sheet)
    app.run_polling()

if __name__ == "__main__":
    main()
