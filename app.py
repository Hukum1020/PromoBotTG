import os
import random
import requests

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ==== Переменные окружения ====
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")
MEDIA_ID           = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD  = os.getenv("DOWNLOAD_PASSWORD")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS_JSON")
SHEET_ID           = os.getenv("SHEET_ID")  # ID вашей Google Sheet

# ==== Подключение к Google Sheets ====
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    data = json.loads(GOOGLE_CREDENTIALS),
    scopes = scope
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1  # либо .worksheet("Лист1") если у вас другой лист

# ==== Сообщения ====
START_MESSAGE = """Привет! 👋  
Ты на шаг ближе к участию…"""
ASK_USERNAME = "Пожалуйста, отправь свой Instagram-никнейм (например, @yourname)"
SUCCESS_MESSAGE_TEMPLATE = """✅ Отлично, все условия выполнены: … *{promo_code}* …"""
FAIL_MESSAGE   = """😕 Ты не выполнил все условия…"""
ALREADY_GOT    = "⚠️ Вы уже получили промокод ранее."
ASK_PASSWORD  = "Пожалуйста, отправь пароль для скачивания файла."
WRONG_PASS    = "🚫 Неверный пароль."
FILE_NOT_FOUND= "🚫 Не удалось получить файл."

# ==== Вспомогательные функции для гугл-таблицы ====
def load_promo_codes():
    """
    Возвращает список свободных кодов [(code, row_index), ...]
    и словарь уже выданных {username: row_index, ...}
    """
    data = ws.get_all_values()
    free = []
    given = {}
    # предположим, заголовок в строке 0, данные с 1
    for i, row in enumerate(data[1:], start=2):
        code = row[0].strip()
        used = row[3].strip() if len(row) > 3 else ""
        if used:
            given[used.lower()] = i
        else:
            free.append((code, i))
    return free, given

def mark_code_as_used(row_index: int, username: str):
    ws.update_cell(row_index, 4, username)  # column D = 4

# ==== Проверка комментария в Instagram ====
def has_user_commented(username: str) -> bool:
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "username,text",
        "limit": 100,
    }
    while url:
        resp = requests.get(url, params=params).json()
        for c in resp.get("data", []):
            if c["username"].lower() == username.lower():
                return True
        url = resp.get("paging", {}).get("next")
    return False

# ==== Хендлеры Telegram ====
async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip("@").lower()
    await update.message.reply_text(f"🔎 Проверяю @{username}…")

    # 1) проверяем Instagram-комментарий
    if not has_user_commented(username):
        return await update.message.reply_text(FAIL_MESSAGE)

    # 2) загружаем список свободных и уже выданных
    free, given = load_promo_codes()

    # 3) если пользователь уже есть в given — шлём ALREADY_GOT
    if username in given:
        return await update.message.reply_text(ALREADY_GOT)

    # 4) иначе — выдаём случайный код и помечаем его
    if not free:
        return await update.message.reply_text("😔 Промокоды закончились.")
    code, row = random.choice(free)
    mark_code_as_used(row, username)
    return await update.message.reply_text(
        SUCCESS_MESSAGE_TEMPLATE.format(promo_code=code),
        parse_mode="Markdown"
    )

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_PASSWORD)
    context.user_data["awaiting_password"] = True

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_password"):
        return  # не ждём пароль — пропускаем
    pwd = update.message.text.strip()
    context.user_data["awaiting_password"] = False

    if pwd != DOWNLOAD_PASSWORD:
        return await update.message.reply_text(WRONG_PASS)

    # экспортируем текущую таблицу в Excel и отсылаем
    # используем встроенный метод gspread + экспорт Google Drive API
    download_url = (
      f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
      "?format=xlsx"
    )
    headers = {"Authorization": f"Bearer {creds.get_access_token().access_token}"}
    resp = requests.get(download_url, headers=headers)
    if resp.status_code == 200:
        # отправляем как документ .xlsx
        return await update.message.reply_document(
            document=resp.content,
            filename="promo_codes.xlsx",
            parse_mode=None
        )
    else:
        return await update.message.reply_text(FILE_NOT_FOUND)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_password))
    # Обработка любого текста после пароля: выдача промокода
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))
    app.run_polling()

if __name__ == "__main__":
    import json
    main()
