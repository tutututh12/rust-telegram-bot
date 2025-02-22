import os
import aiohttp
import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
import asyncio

# 🔑 BattleMetrics API и Telegram Bot Token
BM_API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbiI6IjZlNDhhMmE5ZmMwODVkYjMiLCJpYXQiOjE3NDAxNTE5MzIsIm5iZiI6MTc0MDE1MTkzMiwiaXNzIjoiaHR0cHM6Ly93d3cuYmF0dGxlbWV0cmljcy5jb20iLCJzdWIiOiJ1cm46dXNlcjo5NzAwMTIifQ.ZIIQZJ840bNwXYs6uixudrsiW0g1H_IoVcmTGnSTsN8"
TELEGRAM_BOT_TOKEN = "7804714449:AAFg_4g4HxFqWB9y5IlxGEZePzeiIllvwdo"
BM_API_URL = "https://api.battlemetrics.com/players?filter[search]={steam_id}"
SHOP_API_URL = "https://api.battlemetrics.com/servers/{server_id}/shops"

# 📌 Храним данные
tracked_players = {}  # {steam_id: (server_ip, chat_id)}
tracked_shops = {}  # {server_id: chat_id}
player_status = {}  # {steam_id: is_online}
shop_status = {}  # {server_id: set(shop_positions)}

# 📝 Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# 📂 Подключаем SQLite для хранения истории
conn = sqlite3.connect("player_history.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        steam_id TEXT,
        server_ip TEXT,
        join_time TEXT,
        leave_time TEXT
    )
""")
conn.commit()

async def get_player_info(steam_id: str):
    headers = {"Authorization": f"Bearer {BM_API_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BM_API_URL.format(steam_id=steam_id), headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data"):
                        return data["data"][0]
    except Exception as e:
        logger.error(f"Ошибка при запросе {steam_id}: {e}")
    return None

async def get_shop_info(server_id: str):
    headers = {"Authorization": f"Bearer {BM_API_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHOP_API_URL.format(server_id=server_id), headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return {shop["attributes"]["position"] for shop in data.get("data", [])}
    except Exception as e:
        logger.error(f"Ошибка при запросе магазинов на сервере {server_id}: {e}")
    return set()

async def check_shops_status():
    while True:
        for server_id, chat_id in tracked_shops.items():
            new_shops = await get_shop_info(server_id)
            if server_id not in shop_status:
                shop_status[server_id] = new_shops
            else:
                added_shops = new_shops - shop_status[server_id]
                if added_shops:
                    for shop in added_shops:
                        await send_message(chat_id, f"🛒 Новый магазин появился на сервере {server_id} в квадрате {shop}.")
                shop_status[server_id] = new_shops
        await asyncio.sleep(60)

async def send_message(chat_id, text):
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    await app.bot.send_message(chat_id=chat_id, text=text)

async def track_shop(update: Update, context: CallbackContext):
    if len(context.args) < 1:
        await update.message.reply_text("⚠ Используйте: /trackshop ServerID")
        return

    server_id = context.args[0]
    tracked_shops[server_id] = update.message.chat_id
    await update.message.reply_text(f"🔍 Теперь отслеживаются магазины на сервере {server_id}.")
    logger.info(f"Отслеживаются магазины на сервере {server_id}")

async def menu(update: Update, context: CallbackContext):
    keyboard = [["/track SteamID IP", "/history SteamID"], ["/trackshop ServerID", "/menu"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📌 Доступные команды:", reply_markup=reply_markup)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("👋 Привет! Я бот для отслеживания игроков и магазинов Rust. Используйте /menu для команд.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("trackshop", track_shop))
    app.add_handler(CommandHandler("menu", menu))

    loop = asyncio.get_event_loop()
    loop.create_task(check_shops_status())

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
