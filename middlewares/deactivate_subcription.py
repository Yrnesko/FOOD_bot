import logging
from context import AppContext
from aiomysql import DictCursor
from scheduler import scheduler

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Получение экземпляра планировщик

async def deactivate_expired_subscriptions_task(context: AppContext):
    async with context.pool.acquire() as connection:
        async with connection.cursor(DictCursor) as cursor:
            try:
                logging.info("Проверка просроченных подписок.")
                result = await cursor.execute("""
                    UPDATE subscriptions
                    SET is_active = FALSE
                    WHERE end_date < NOW() AND is_active = TRUE;
                """)
                await connection.commit()
                logging.info(f"Деактивировано подписок: {result}")
            except Exception as e:
                logging.error(f"Ошибка при деактивации подписок: {e}")

async def schedule_subscription_check(context: AppContext, interval_minutes: int = 59):
    scheduler.add_job(
        deactivate_expired_subscriptions_task,
        trigger='interval',
        minutes=interval_minutes,
        args=[context],
        id='deactivate_expired_subscriptions',
        replace_existing=True
    )
    logging.info(f"Задача деактивации подписок запланирована на каждые {interval_minutes} минут.")

