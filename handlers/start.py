from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states import UserData
import aiomysql
import logging
from context import AppContext
from datetime import datetime, timedelta
from scheduler import scheduler


#scheduler = SchedulerSingleton().scheduler

async def send_welcome(message: types.Message, context: AppContext = None):
    keyboard = InlineKeyboardMarkup()
    intro_button = InlineKeyboardButton("Познакомиться", callback_data="introduce")
    keyboard.add(intro_button)
    await message.answer_photo(
        photo="https://i.imgur.com/C31Zmpq.jpeg",
        caption=(
            "Поздравляю, Вы на пути к здоровому телу мечты🔥\n\n"
            "Давайте знакомиться, я - бот Ирины Олейник. Я буду вашим карманным диетологом и помогу вам достичь желаемого веса.\n\n"
            "👉 Нам предстоит увлекательный путь"
        ),
        reply_markup=keyboard
    )

async def on_start(message: types.Message, state: FSMContext = None, context: AppContext = None):
    tg_user_id = message.from_user.id
    async with context.pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("SELECT is_registered FROM users WHERE tg_user_id = %s", (tg_user_id,))
                user = await cursor.fetchone()

                if user is not None and user[0] == 1:
                    current_state = await state.get_state()
                    logging.info(f"текущее состояние {message.from_user.id}: {current_state}")
                    await message.answer(
                        "Теперь вам доступна кнопка «Меню», она находится слева снизу и выделяется синим цветом ‼️\n\n"
                        "1️⃣ Если вы захотите изменить время приема пищи, напишите мне кодовое слово \"Завтрак / Обед / Ужин\".\n\n"
                        "2️⃣ Если вы захотите поесть раньше назначенного времени, нажмите «меню»."
                    )

                else:
                    await send_welcome(message, context)
                    # Запланировать отправку повторного сообщения через 15 минут
                    scheduler.add_job(send_reminder, "date", run_date=datetime.now() + timedelta(minutes=30), args=[tg_user_id, context])
            except aiomysql.MySQLError as err:
                await message.answer(f"Произошла ошибка при обращении к базе данных: {err}")

async def send_reminder(user_id: int, context: AppContext):
    try:
        bot = context.dispatcher.bot
        async with context.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT is_registered FROM users WHERE tg_user_id = %s", (user_id,))
                user = await cursor.fetchone()

                if user is None:
                    keyboard = InlineKeyboardMarkup()
                    intro_button = InlineKeyboardButton("Познакомиться", callback_data="introduce")
                    keyboard.add(intro_button)

                    logging.info(f"Отправка напоминания пользователю {user_id}")

                    await bot.send_message(
                        user_id,  # Используем user_id как chat_id
                        "Хоть боты и не умеют грустить, я очень расстроен,\n"
                        "что мы так и не познакомились 😢\n"
                        "Чтобы продолжить наше знакомство, просто нажми на кнопочку ниже",
                        reply_markup=keyboard
                    )
                    logging.info(f"Сообщение отправлено пользователю {user_id} успешно")
    except Exception as e:
        logging.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")





async def handle_intro(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    tg_user_id = callback_query.from_user.id
    username = callback_query.from_user.first_name
    logging.info(f"Получено введение от пользователя {tg_user_id}. Никнейм: {username}")

    async with context.pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("SELECT is_registered FROM users WHERE tg_user_id = %s", (tg_user_id,))
                user = await cursor.fetchone()

                if user is None:
                    await cursor.execute("INSERT INTO users (tg_user_id, username, is_registered) VALUES (%s, %s, 0)",
                                       (tg_user_id, username))
                else:
                    await cursor.execute("UPDATE users SET username = %s WHERE tg_user_id = %s", (username, tg_user_id))

                await connection.commit()
            except aiomysql.MySQLError as err:
                logging.error(f"Ошибка в базе данных: {err}")

    await callback_query.message.edit_reply_markup()
    await callback_query.message.answer_photo(
        photo="https://i.imgur.com/bhM3Kss.png",
        caption=(
            f"Приятно познакомиться, {username}! Осталось немного, чтобы завершить регистрацию.\n\n"
            "А теперь давайте определимся, какую норму калорий в сутки вам необходимо получать.\n\n"
            "Напишите мне, какой у Вас рост?"
        )
    )

    await state.update_data(tg_user_id=tg_user_id, username=username)
    await state.set_state(UserData.waiting_for_height)

    logging.info(f"State set to UserData:waiting_for_height for user {tg_user_id}")

def register_start_handler(context: AppContext):
    dp = context.dispatcher
    dp.register_message_handler(lambda msg, state=None: on_start(msg, state, context), Command("start"))
    dp.register_callback_query_handler(lambda cb, state=None: handle_intro(cb, state, context), lambda c: c.data == "introduce")
