import random
import requests
import os
import logging
from openpyxl import load_workbook
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)

# --- Переменные окружения ---
ACCESS_TOKEN     = os.getenv("ACCESS_TOKEN")
MEDIA_ID         = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD= os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE       = "promo_codes_test.xlsx"
SHEET_NAME       = "Лист1"

# --- Сообщения ---
START_MESSAGE = (
    "Привет! 👋\n"
    "Чтобы получить промокод, просто пришли свой Instagram-никнейм (например, @yourname).\n"
)
ALREADY_GOT       = "❗️ Вы уже получили промокод ранее."
SUCCESS_TEMPLATE  = "✅ Ваш промокод: *{promo_code}*"
FAIL_MESSAGE      = (
    "😕 Комментарий под постом не найден. Проверь, пожалуйста, что ты:\n"
    "1. Подписан на @aviashow.kz\n"
    "2. Лайкнул пост\n"
    "3. Оставил комментарий с отметкой 2 друзей"
)
ASK_DOWNLOAD_PASS = "Пожалуйста, отправьте пароль для скачивания файла."
WRONG_PASS        = "🚫 Неверный пароль."
FILE_NOT_FOUND    = "🚫 Файл не найден на сервере."

# --- Помощники работы с Excel ---
def load_promo_codes():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    free_codes = []
    for row in ws.iter_rows(min_row=2):
        code = row[0].value
        used = row[3].value  # колонка D (Used)
        if code and not used:
            free_codes.append((code, row[0].row))
    wb.close()
    return free_codes

def mark_code_as_used(row_number: int, username: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row_number, column=4, value=username)  # пишем в D
    wb.save(EXCEL_FILE)
    wb.close()

def is_user_in_table(username: str) -> bool:
    wb = load_workbook(EXCEL_FILE, read_only=True)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2):
        if row[3].value and row[3].value.lower() == username.lower():
            wb.close()
            return True
    wb.close()
    return False

# --- Проверка комментариев в Instagram ---
def has_user_commented(username: str) -> bool:
    """
    Дополнительно логируем всех найденных в посте комментаторов для дебага.
    """
    url = f"https://graph.facebook.com/v22.0/{MEDIA_ID}/comments"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "username,text",
        "limit": 100,
    }
    all_usernames = []
    while url:
        resp = requests.get(url, params=params)
        data = resp.json()
        # Собираем всех имён
        for c in data.get("data", []):
            u = c.get("username", "")
            all_usernames.append(u)
        url = data.get("paging", {}).get("next")

    logging.info(f"🛠 Debug — все найденные юзеры в комментариях: {all_usernames}")

    # проверяем, есть ли наш ник среди них
    return username.lower() in [u.lower() for u in all_usernames]

# --- Обработчики Telegram ---
async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip("@")
    logging.info(f"Проверяю комментарий от @{username}…")
    # 1. уже получал?
    if is_user_in_table(username):
        await update.message.reply_text(ALREADY_GOT)
        return

    # 2. есть ли коммент?
    if not has_user_commented(username):
        await update.message.reply_text(FAIL_MESSAGE)
        return

    # 3. выдаём случайный код
    free_codes = load_promo_codes()
    if not free_codes:
        await update.message.reply_text("😔 Промокоды закончились.")
        return

    promo, row = random.choice(free_codes)
    mark_code_as_used(row, username)
    await update.message.reply_text(
        SUCCESS_TEMPLATE.format(promo_code=promo),
        parse_mode="Markdown"
    )

async def download_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ASK_DOWNLOAD_PASS)
    context.user_data["awaiting_pass"] = True

async def download_check_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_pass"):
        return  # игнорируем, если мы не ждали пароль

    context.user_data["awaiting_pass"] = False
    pw = update.message.text.strip()
    if pw != DOWNLOAD_PASSWORD:
        await update.message.reply_text(WRONG_PASS)
        return

    if not os.path.exists(EXCEL_FILE):
        await update.message.reply_text(FILE_NOT_FOUND)
        return

    # Отправляем файл .xlsx
    await update.message.reply_document(InputFile(EXCEL_FILE), filename="promo_codes.xlsx")

# --- Точка входа ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # /download
    app.add_handler(CommandHandler("download", download_start))
    # проверяем пароль
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(fr"^{DOWNLOAD_PASSWORD}$"),
        download_check_pass
    ))

    # все остальные текстовые сообщения — это инста-ник
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))

    app.run_polling()

if __name__ == "__main__":
    main()
