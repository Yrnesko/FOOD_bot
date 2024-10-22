import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states import UserData
import aiomysql
from scheduler import add_daily_task
from database.database import get_meals_per_day, get_user_id_by_tg_user_id, get_tg_user_id_by_user_id
from datetime import timedelta
import pytz
from context import AppContext
from functools import partial
from datetime import datetime

logging.basicConfig(level=logging.INFO)

def generate_change_options_keyboard(meals_per_day):
    keyboard = InlineKeyboardMarkup(row_width=2)
    if meals_per_day > 1:
        keyboard.add(
            InlineKeyboardButton(text="Завтрак", callback_data="change_breakfast_time"),
            InlineKeyboardButton(text="Ужин", callback_data="change_dinner_time")
        )
        if meals_per_day == 3:
            keyboard.add(
                InlineKeyboardButton(text="Обед", callback_data="change_lunch_time")
            )
    keyboard.add(
        InlineKeyboardButton(text="Часовой пояс", callback_data="change_timezone")
    )
    return keyboard


async def show_change_options(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    meals_per_day = data.get('meals_per_day', 3)
    await callback_query.message.edit_text(
        "Что хотите изменить?",
        reply_markup=generate_change_options_keyboard(meals_per_day)
    )
    await state.set_state(UserData.editing_options)


def generate_timezone_keyboard():
    timezones = [
        "UTC+2 (Калининградское время)", "UTC+3 (Московское время)", "UTC+4 (Самарское время)",
        "UTC+5 (Екатеринбургское время)", "UTC+6 (Омское время)", "UTC+7 (Красноярское время)",
        "UTC+8 (Иркутское время)", "UTC+9 (Якутское время)", "UTC+10 (Владивостокское время)",
        "UTC+11 (Магаданское время)", "UTC+12 (Камчатское время)", "UTC+14 (Чукотское время)"
    ]
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=tz, callback_data=f"tz_{tz.split()[0]}") for tz in timezones]
    keyboard.add(*buttons)
    return keyboard

def generate_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="Продолжить", callback_data="confirm"),
        InlineKeyboardButton(text="Изменить данные", callback_data="edit")
    )
    return keyboard

async def choose_timezone(message: types.Message, state: FSMContext):
    await message.edit_text("Пожалуйста, выберите ваш часовой пояс:", reply_markup=generate_timezone_keyboard())
    await state.set_state(UserData.waiting_for_timezone)
    logging.info(f"State set to waiting_for_timezone for user {message.from_user.id}.")

async def set_timezone(callback_query: types.CallbackQuery, state: FSMContext):
    timezone = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id

    logging.info(f"User {user_id} selected timezone: {timezone}")

    await state.update_data(timezone=timezone)
    await callback_query.message.edit_text(f"Вы выбрали часовой пояс: {timezone}. Хорошо! Последнее уточнение выберите время для завтрака ⏰ (в формате 10:00):")
    await state.set_state(UserData.waiting_for_breakfast_time)
    logging.info(f"State set to waiting_for_breakfast_time for user {user_id}.")

async def set_breakfast_time(message: types.Message, state: FSMContext, context:AppContext):
    pool = context.pool
    meal_time = message.text.strip()
    user_id = message.from_user.id

    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(breakfast_time=meal_time)
    user_id_v2 = await get_user_id_by_tg_user_id(pool, user_id)
    meals_per_day = await get_meals_per_day(pool, user_id_v2)
    meals_per_day = int(meals_per_day)

    if meals_per_day == 2:
        await message.answer("Хорошо, и, наконец, выберите время для ужина⏰ (в формате 19:00):")
        await state.set_state(UserData.waiting_for_dinner_time)
        logging.info(f"State set to waiting_for_dinner_time for user {user_id}.")
    elif meals_per_day == 3:
        await message.answer("Хорошо, выберите время для обеда ⏰ (в формате 14:00):")
        await state.set_state(UserData.waiting_for_lunch_time)
        logging.info(f"State set to waiting_for_lunch_time for user {user_id}.")
    else:
        logging.info(f"Unexpected meals_per_day value: {meals_per_day}")

async def set_lunch_time(message: types.Message, state: FSMContext):
    meal_time = message.text.strip()
    user_id = message.from_user.id

    logging.info(f"User {user_id} entered lunch time: {meal_time}")

    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(lunch_time=meal_time)
    await message.answer("Хорошо, и, наконец, выберите время для ужина⏰ (в формате 19:00):")
    await state.set_state(UserData.waiting_for_dinner_time)
    logging.info(f"State set to waiting_for_dinner_time for user {user_id}.")

async def set_dinner_time(message: types.Message, state: FSMContext):
    meal_time = message.text.strip()
    user_id = message.from_user.id

    logging.info(f"User {user_id} entered dinner time: {meal_time}")

    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(dinner_time=meal_time)
    await state.update_data(user_id=user_id)
    await show_confirmation(message, state)

async def change_option_callback(callback_query: types.CallbackQuery, state: FSMContext):
    callback_data = callback_query.data
    logging.info(f"Пользователь {callback_query.from_user.id} выбранный вариант для изменения: {callback_data}")

    current_state = await state.get_state()
    logging.info(f"Текущее состояние перед изменением параметра: {current_state}")

    # Обработка выбора опций для изменения времени
    if callback_data == "change_breakfast_time":
        await callback_query.message.answer("Введите новое время для завтрака (в формате HH:MM):")
        await state.set_state(UserData.changing_breakfast_time)
    elif callback_data == "change_lunch_time":
        await callback_query.message.answer("Введите новое время для обеда (в формате HH:MM):")
        await state.set_state(UserData.changing_lunch_time)
    elif callback_data == "change_dinner_time":
        await callback_query.message.answer("Введите новое время для ужина (в формате HH:MM):")
        await state.set_state(UserData.changing_dinner_time)
    elif callback_data == "change_timezone":
        await callback_query.message.answer(
            "Пожалуйста, выберите ваш часовой пояс:",
            reply_markup=generate_timezone_keyboard()
        )
        await state.set_state(UserData.changing_timezone)

    new_state = await state.get_state()
    logging.info(f"Новое состояние после изменения параметра: {new_state}")


async def change_breakfast_time(message: types.Message, state: FSMContext):
    meal_time = message.text.strip()
    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(breakfast_time=meal_time)
    await message.answer("Время для завтрака обновлено.")
    await show_confirmation(message, state)

async def change_lunch_time(message: types.Message, state: FSMContext):
    meal_time = message.text.strip()
    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(lunch_time=meal_time)
    await message.answer("Время для обеда обновлено.")
    await show_confirmation(message, state)

async def change_dinner_time(message: types.Message, state: FSMContext):
    meal_time = message.text.strip()
    if not validate_time_format(meal_time):
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
        return

    await state.update_data(dinner_time=meal_time)
    await message.answer("Время для ужина обновлено.")
    await show_confirmation(message, state)


async def change_timezone(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info(f"Callback query data: {callback_query.data}")
    # Извлечение нового часового пояса
    timezone = callback_query.data.split("_")[1]
    await state.update_data(timezone=timezone)
    await callback_query.message.answer(f"Часовой пояс изменен на: {timezone}")
    await show_confirmation(callback_query.message, state)

async def show_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    timezone = data.get('timezone', 'не установлено')
    breakfast_time = data.get('breakfast_time', 'не установлено')
    lunch_time = data.get('lunch_time')
    dinner_time = data.get('dinner_time', 'не установлено')

    confirmation_text = f"Ваши настройки:\nЧасовой пояс: {timezone}\n"

    # Добавляем информацию о времени завтрака
    confirmation_text += f"Завтрак: {breakfast_time}\n"

    # Добавляем информацию о времени обеда, если он установлен
    if lunch_time:
        confirmation_text += f"Обед: {lunch_time}\n"

    # Добавляем информацию о времени ужина
    confirmation_text += f"Ужин: {dinner_time}\n\n"

    # Финальная часть сообщения
    confirmation_text += "Все верно?"

    await message.answer(confirmation_text, reply_markup=generate_confirmation_keyboard())
    await state.set_state(UserData.confirming_meal_times)



async def confirm_data(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    if callback_query.data == "confirm":
        await save_meal_times(callback_query.message, state, context)
    elif callback_query.data == "edit":
        await show_change_options(callback_query, state)


async def save_meal_times(message: types.Message, state: FSMContext, context: AppContext):
    data = await state.get_data()
    user_id = data.get('user_id', message.from_user.id)
    logging.info(f"user id = {user_id}")


    breakfast_time = data.get('breakfast_time')
    lunch_time = data.get('lunch_time')
    dinner_time = data.get('dinner_time')
    timezone = data.get('timezone')

    logging.info(
        f"Saving meal times for user {user_id}: breakfast_time={breakfast_time}, lunch_time={lunch_time}, dinner_time={dinner_time}, timezone={timezone}"
    )
    try:
        async with context.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                logging.info(f"Querying for user_id: {user_id}")
                await cursor.execute("SELECT id FROM users WHERE tg_user_id = %s", (user_id,))
                user_id_db = await cursor.fetchone()

                if not user_id_db:
                    await message.answer("Пользователь не найден в базе данных.")
                    logging.info(f"User with tg_user_id {user_id} not found.")
                    return

                user_id_db = user_id_db[0]

                # Преобразование времени в формат TIME и в объект time
                def str_to_time(time_str):
                    if time_str:
                        return datetime.strptime(time_str, '%H:%M:%S').time()
                    return None

                breakfast_time_utc = convert_to_utc(breakfast_time, timezone).strftime('%H:%M:%S') if breakfast_time else None
                lunch_time_utc = convert_to_utc(lunch_time, timezone).strftime('%H:%M:%S') if lunch_time else None
                dinner_time_utc = convert_to_utc(dinner_time, timezone).strftime('%H:%M:%S') if dinner_time else None

                breakfast_time_obj = str_to_time(breakfast_time_utc)
                lunch_time_obj = str_to_time(lunch_time_utc)
                dinner_time_obj = str_to_time(dinner_time_utc)

                update_query = """
                    UPDATE meal_schedules
                    SET breakfast_time = %s, lunch_time = %s, dinner_time = %s, user_timezone = %s
                    WHERE user_id = %s
                """
                await cursor.execute(update_query, (breakfast_time_utc, lunch_time_utc, dinner_time_utc, timezone, user_id_db))

                if cursor.rowcount == 0:
                    insert_query = """
                        INSERT INTO meal_schedules (user_id, breakfast_time, lunch_time, dinner_time, user_timezone)
                        VALUES (%s, %s, %s, %s, %s) AS new_data
                        ON DUPLICATE KEY UPDATE 
                            breakfast_time = new_data.breakfast_time,
                            lunch_time = new_data.lunch_time, 
                            dinner_time = new_data.dinner_time, 
                            user_timezone = new_data.user_timezone
                    """
                    await cursor.execute(insert_query,
                                         (user_id_db, breakfast_time_utc, lunch_time_utc, dinner_time_utc, timezone))

                await conn.commit()
                logging.info(f"Meal times for user {user_id} saved successfully.")
                await message.edit_text(
                    "Теперь вам доступна кнопка «Меню», она находится слева снизу и выделяется синим цветом ‼️\n\n"
                    "1️⃣ Если вы захотите изменить время приема пищи, напишите мне кодовое слово \"Завтрак / Обед / Ужин\".\n\n"
                    "2️⃣ Если вы захотите поесть раньше назначенного времени, нажмите «меню»."
                )

                if breakfast_time_obj:
                    await add_daily_task(context, user_id_db, breakfast_time_obj,  task_type="breakfast")

                if lunch_time_obj:
                    await add_daily_task(context, user_id_db, lunch_time_obj, task_type="lunch")

                if dinner_time_obj:
                    await add_daily_task(context, user_id_db, dinner_time_obj, task_type="dinner")

                await state.finish()
                current_state = await state.get_state()
                logging.info(f"Текущее состояние  {message.from_user.id}: {current_state}")

    except aiomysql.MySQLError as err:
        logging.error(f"Database error: {err}")
        await message.answer("Произошла ошибка при сохранении данных. Попробуйте еще раз позже.")

def convert_to_utc(user_time_str, user_offset):
    """Преобразует время пользователя в UTC, используя смещение."""
    logging.debug(f"Converting time: {user_time_str} with offset: {user_offset}")

    try:
        # Проверка формата времени
        if not validate_time_format(user_time_str):
            raise ValueError(f"Invalid time format: {user_time_str}")

        # Преобразование строки времени в объект времени
        user_time = datetime.strptime(user_time_str, "%H:%M").time()
        user_datetime = datetime.combine(datetime.today(), user_time)
        logging.debug(f"User datetime: {user_datetime}")

        # Обработка смещения
        if user_offset.startswith('UTC'):
            offset_str = user_offset[3:]  # Получаем часть строки после 'UTC'
        else:
            offset_str = user_offset
        logging.debug(f"Offset after 'UTC': {offset_str}")

        # Преобразование смещения в формат ±HH:MM
        if offset_str[0] in ['+', '-']:
            if len(offset_str) == 2:  # Например, '+07'
                user_offset_str = f"{offset_str[:1]}{offset_str[1:]}:00"
            elif len(offset_str) == 5:  # Например, '+07:00'
                user_offset_str = offset_str
            else:
                raise ValueError(f"Invalid offset format: {user_offset}")
        else:
            raise ValueError(f"Invalid offset format: {user_offset}")

        # Извлечение часов и минут из строки смещения
        hours, minutes = map(int, user_offset_str.split(':'))
        offset = timedelta(hours=hours, minutes=minutes)
        total_minutes = int(offset.total_seconds() / 60)
        logging.debug(f"Offset in minutes: {total_minutes}")

        # Преобразование смещения в FixedOffset
        user_timezone = pytz.FixedOffset(total_minutes)
        local_datetime = user_timezone.localize(user_datetime)
        logging.debug(f"Local datetime with timezone: {local_datetime}")

        # Преобразование времени в UTC
        utc_datetime = local_datetime.astimezone(pytz.utc)
        logging.debug(f"Converted UTC datetime: {utc_datetime}")

        return utc_datetime

    except Exception as e:
        logging.error(f"Error converting to UTC: {e}")
        raise

def validate_time_format(time_str):
    """Проверяет формат времени."""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False



def register_meal_schedule_handlers(context: AppContext):
    dp = context.dispatcher
    dp.register_message_handler(choose_timezone, commands="set_meal_times", state="*")
    dp.register_callback_query_handler(set_timezone, lambda c: c.data.startswith("tz_"), state=UserData.waiting_for_timezone)
    dp.register_message_handler(partial(set_breakfast_time, context=context), state=UserData.waiting_for_breakfast_time)
    dp.register_message_handler(set_lunch_time, state=UserData.waiting_for_lunch_time)
    dp.register_message_handler(set_dinner_time, state=UserData.waiting_for_dinner_time)
    dp.register_callback_query_handler(change_option_callback, state=UserData.editing_options)
    dp.register_message_handler(change_breakfast_time, state=UserData.changing_breakfast_time)
    dp.register_message_handler(change_lunch_time, state=UserData.changing_lunch_time)
    dp.register_message_handler(change_dinner_time, state=UserData.changing_dinner_time)
    dp.register_callback_query_handler(change_timezone, lambda c: c.data.startswith("tz_"), state=UserData.changing_timezone)
    dp.register_callback_query_handler(
        partial(confirm_data, context=context),
        lambda c: c.data in ["confirm", "edit"],
        state=UserData.confirming_meal_times
    )

