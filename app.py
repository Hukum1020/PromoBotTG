import random
import requests
import os
from openpyxl import load_workbook
from telegram import Update, InputFile, Bot
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# --- настройки из среды ---
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")
MEDIA_ID           = os.getenv("MEDIA_ID")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
DOWNLOAD_PASSWORD  = os.getenv("DOWNLOAD_PASSWORD")

EXCEL_FILE = "promo_codes_test.xlsx"
SHEET_NAME = "Лист1"

# --- тексты ---
START_MESSAGE = """Привет! 👋  
Напиши свой Instagram-никнейм (например, @yourname), и я проверю, оставил ли ты комментарий под нашим розыгрышем."""
ALREADY_GOT = "❗️ Вы уже получили промокод ранее: *{promo_code}*"
SUCCESS_MESSAGE = """✅ Отлично! Вот твой промокод: *{promo_code}*"""
FAIL_MESSAGE = """😕 Комментарий под постом не найден. Проверь, пожалуйста, что ты:
1. Подписан на @aviashow.kz  
2. Лайкнул пост  
3. Оставил комментарий с отметкой 2 друзей"""
ASK_PASSWORD = "🔒 Введите пароль для скачивания файла."
WRONG_PASSWORD = "🚫 Неверный пароль."
FILE_NOT_FOUND = "🚫 Файл не найден."

# --- работа с Excel ---
def load_promo_data():
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    records = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        code_cell = row[0]
        used_cell = row[3]
        records.append({
            "code": code_cell.value,
            "used": used_cell.value,
            "row": code_cell.row
        })
    wb.close()
    return records

def save_used(row: int, username: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb[SHEET_NAME]
    ws.cell(row=row, column=4, value=username)
    wb.save(EXCEL_FILE)
    wb.close()

# --- проверка комментария в Instagram ---
def has_commented(username: str) -> bool:
    url = f"https://graph.facebook.com/v19.0/{MEDIA_ID}/comments"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "username,text",
        "limit": 100
    }
    while url:
        r = requests.get(url, params=params).json()
        for c in r.get("data", []):
            if c["username"].lower() == username.lower():
                return True
        url = r.get("paging", {}).get("next")
    return False

# --- обработчики ---
async def cmd_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_password"] = True
    await update.message.reply_text(ASK_PASSWORD)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # 1) Сейчас ждём пароль?
    if context.user_data.get("awaiting_password"):
        context.user_data["awaiting_password"] = False
        if text == DOWNLOAD_PASSWORD:
            if os.path.exists(EXCEL_FILE):
                await update.message.reply_document(InputFile(EXCEL_FILE, filename="promo_codes.xlsx"))
            else:
                await update.message.reply_text(FILE_NOT_FOUND)
        else:
            await update.message.reply_text(WRONG_PASSWORD)
        return

    # 2) Иначе — это никнейм для розыгрыша.
    username = text.lstrip("@")
    await update.message.reply_text(f"🔍 Проверяю комментарий от @{username}…")

    # сначала проверяем, не брал ли он уже
    data = load_promo_data()
    for rec in data:
        if rec["used"] and rec["used"].lower() == username.lower():
            # нашли в колонке used
            await update.message.reply_text(ALREADY_GOT.format(promo_code=rec["code"]), parse_mode="Markdown")
            return

    # если не брали, проверяем комментарий в инсте
    if not has_commented(username):
        await update.message.reply_text(FAIL_MESSAGE)
        return

    # выдаём случайный свободный код
    free = [r for r in data if not r["used"]]
    if not free:
        await update.message.reply_text("😔 Промокоды закончились.")
        return

    rec = random.choice(free)
    save_used(rec["row"], username)
    await update.message.reply_text(SUCCESS_MESSAGE.format(promo_code=rec["code"]), parse_mode="Markdown")

def run_bot():
    # чистим возможный старый webhook
    bot = Bot(token=TELEGRAM_TOKEN)
    bot.delete_webhook(drop_pending_updates=True)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("download", cmd_download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    run_bot()
