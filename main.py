import asyncio
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import register_handlers
from scheduler import start_scheduler, load_tasks_from_db, schedule_task_reload, log_all_jobs
from context import AppContext
from database.database import create_pool
import logging
from middlewares.deactivate_subcription import schedule_subscription_check
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def on_startup(context: AppContext):
    await start_scheduler()
    await schedule_subscription_check(context)
    await load_tasks_from_db(context)
    await schedule_task_reload(context)
    await log_all_jobs()


async def main():
    pool = await create_pool()
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(bot, storage=storage)

    # Создаем контекст и передаем пул соединений
    context = AppContext(dispatcher=dp, pool=pool)

    try:
        # Запускаем задачи при старте
        await on_startup(context)

        # Регистрируем обработчики
        register_handlers(context)

        # Запускаем бота
        await dp.start_polling()
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
    finally:
        # Закрываем сессию бота
        await bot.session.close()

        # Закрываем пул соединений
        if pool:
            pool.close()
            await pool.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
