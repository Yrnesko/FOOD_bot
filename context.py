import asyncio
import time
import logging
from aiogram import Dispatcher
import aiomysql

logger = logging.getLogger(__name__)

class AppContext:
    def __init__(self, dispatcher: Dispatcher, pool: aiomysql.Pool):
        self.dispatcher = dispatcher
        self.pool = pool
        self.second_breakfast_chosen = {}
        self.last_update = {}
        self.lock = asyncio.Lock()  # Создаем асинхронную блокировку

    async def set_second_breakfast_chosen(self, user_id: int, chosen: bool):
        async with self.lock:  # Используем блокировку
            self.second_breakfast_chosen[user_id] = chosen
            self.last_update[user_id] = time.time()  # Обновляем время последнего изменения
            logger.info(f"Установлено состояние второго завтрака для пользователя {user_id}: {chosen}")
            logger.info(f"Время последнего обновления для пользователя {user_id}: {self.last_update[user_id]}")

    async def get_second_breakfast_chosen(self, user_id: int):
        async with self.lock:  # Используем блокировку
            # Проверяем, не истек ли срок действия кеша
            if user_id in self.last_update:
                if time.time() - self.last_update[user_id] < 10 * 3600:  # 10 часов
                    chosen = self.second_breakfast_chosen.get(user_id, False)
                    logger.info(f"Получено состояние второго завтрака для пользователя {user_id}: {chosen}")
                    return chosen
                else:
                    # Удаляем устаревший кеш
                    logger.info(f"Кеш для пользователя {user_id} устарел и удален.")
                    del self.second_breakfast_chosen[user_id]
                    del self.last_update[user_id]
            else:
                logger.info(f"Кеш для пользователя {user_id} не найден.")
            return False
