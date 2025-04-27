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

# --- Логирование ---
def setup_logging():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.INFO
    )

# --- Переменные окружения ---
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")
MEDIA_ID           = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD  = os.getenv("DOWNLOAD_PASSWORD")
CREDENTIALS_JSON   = os.getenv("GOOGLE_CREDENTIALS")
SPREADSHEET_ID     = os.getenv("SHEET_ID")

# --- Тексты ---
START_MESSAGE = """Привет! 👋  
Ты на шаг ближе к участию в розыгрыше VIP-билетов на авиашоу «Небо Байсерке – 2025» ✈🎁
Каждый участник получает ПОДАРОК — промокод на скидку 10% на стандартный билет!
Перед тем как выдать тебе промокод, давай проверим, что ты выполнил все условия 👇
"""
ASK_USERNAME = "Пожалуйста, отправь свой Instagram-никнейм (например, @yourname)"
SUCCESS_MESSAGE_TEMPLATE = """✅ Отлично, все условия выполнены:
• Подписка на @aviashow.kz  
• Лайк на пост с розыгрышем  
• Комментарий с отметкой двух друзей  
🎁 Вот твой персональный промокод: *{promo_code}*"""
FAIL_MESSAGE = """😕 Ты не выполнил все условия.  
1. Подписан на @aviashow.kz  
2. Лайкнул пост  
3. Отметил 2 друзей  
🔁 Когда всё будет готово — просто отправь свой ник снова."""
ASK_PASS     = "Пожалуйста, отправьте пароль для скачивания файла."
WRONG_PASS   = "🚫 Неверный пароль. Попробуйте снова."
FILE_MISSING = "🚫 Файл не найден."

# --- Google Sheets init ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
def init_sheet():
    if not CREDENTIALS_JSON:
        raise ValueError("❌ Не задана переменная GOOGLE_CREDENTIALS")
    try:
        creds_dict = json.loads(CREDENTIALS_JSON)
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        raise ValueError(f"❌ Ошибка Google Sheets: {e}")

# --- Работа с промокодами ---
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

# --- Инстаграм ---
def has_user_commented(username):
    url = f"https://graph.facebook.com/v22.0/{MEDIA_ID}/comments"
    params = {"access_token": ACCESS_TOKEN, "fields": "username,text", "limit": 100}
    commenters = []
    while url:
        resp = requests.get(url, params=params).json()
        for c in resp.get("data", []):
            commenters.append(c.get("username", "").lower())
        url = resp.get("paging", {}).get("next")
    logging.info(f"🛠 Debug — все найденные юзеры: {commenters}")
    return username.lower() in commenters

# --- Хендлеры Telegram ---
def register_handlers(app, sheet):

    # /start
    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # сбросим флаги
        context.user_data.clear()
        await update.message.reply_text(START_MESSAGE)
        await update.message.reply_text(ASK_USERNAME)

    # /download
    async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["awaiting_password"] = True
        await update.message.reply_text(ASK_PASS)

    # общий обработчик всех прочих сообщений
    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()

        # 1) если ждём пароль
        if context.user_data.get("awaiting_password"):
            context.user_data["awaiting_password"] = False
            if text == DOWNLOAD_PASSWORD:
                # скачиваем xlsx
                url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
                token = sheet.client.auth.access_token
                r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    await update.message.reply_document(
                        document=r.content, filename="promo_codes.xlsx"
                    )
                else:
                    await update.message.reply_text(FILE_MISSING)
            else:
                await update.message.reply_text(WRONG_PASS)
            return

        # 2) если это команда (но не /start или /download) — игнорируем
        if text.startswith("/"):
            return

        # 3) обработка никнейма
        username = text.lstrip("@").lower()

        free, given = load_promo_codes(sheet)
        if username in given:
            await update.message.reply_text(
                f"👀 Вы уже получили промокод: {given[username]}"
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

    # регистрация
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("download", download_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

# --- Запуск ---
def main():
    setup_logging()
    sheet = init_sheet()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app, sheet)
    app.run_polling()

if __name__ == "__main__":
    main()
