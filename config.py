import os
from dotenv import load_dotenv
load_dotenv()

# Получение токенов и данных из окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")

# Конфигурация для базы данных
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

def get_db_config():
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME,
    }

# Асинхронная функция для проверки соединения с базой данных
async def check_db_connection(pool):
    try:
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT VERSION()")
                db_info = await cursor.fetchone()
                print(f"Successfully connected to MySQL database. MySQL Server version: {db_info[0]}")
                return True
    except Exception as e:
        print(f"Error: {e}")
        return False
