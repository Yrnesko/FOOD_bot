import aiomysql
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram import types, Dispatcher
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.storage import FSMContext
import logging
from states import UserData
from menu.menu_messages import generate_subscription_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, dp: Dispatcher, pool):
        super(SubscriptionMiddleware, self).__init__()
        self.dp = dp
        self.pool = pool  # Сохраняем пул соединений
        self.excluded_states = [
            UserData.managing_subscription.state
        ]

    async def on_process_callback_query(self, query: types.CallbackQuery, data: dict):
        await self.check_subscription(query.message, query.from_user.id)

    async def on_process_message(self, message: types.Message, data: dict):
        await self.check_subscription(message, message.from_user.id)

    async def check_subscription(self, entity: types.Message, user_id: int):
        state = FSMContext(storage=self.dp.storage, chat=entity.chat.id, user=user_id)
        current_state = await state.get_state()

        if current_state in self.excluded_states:
            return

        try:
            # Используем пул соединений
            async with self.pool.acquire() as connection:
                async with connection.cursor(aiomysql.DictCursor) as cursor:

                    # Выполняем первый запрос и обрабатываем результат
                    await cursor.execute("SELECT * FROM users WHERE tg_user_id = %s", (user_id,))
                    user = await cursor.fetchone()
                    if not user or not user.get('is_registered'):
                        return  # Пользователь не зарегистрирован, позволяем продолжить

                    # Выполняем второй запрос и обрабатываем результат
                    await cursor.execute("SELECT * FROM subscriptions WHERE user_id = %s", (user['id'],))
                    subscription_user = await cursor.fetchone()
                    if not subscription_user:
                        return  # Пользователь не найден в таблице subscriptions, позволяем продолжить

                    # Выполняем третий запрос и обрабатываем результат
                    await cursor.execute("""
                        SELECT * FROM subscriptions 
                        WHERE user_id = %s AND is_active = TRUE AND end_date > NOW()
                    """, (user['id'],))
                    subscription = await cursor.fetchone()
                    if not subscription:
                        await entity.answer("У вас нет активной подписки. Пожалуйста, оформите подписку.",
                                            reply_markup=generate_subscription_keyboard())

                        await state.set_state(UserData.managing_subscription.state)
                        new_state = await state.get_state()
                        logger.info(f"Новое состояние пользователя {user_id}: {new_state}")
                        raise CancelHandler()

        except aiomysql.Error as err:
            logger.error(f"Ошибка базы данных: {err}")
