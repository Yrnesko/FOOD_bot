from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram import types, Dispatcher
from aiogram.dispatcher.handler import CancelHandler
import logging
from functools import partial
from context import AppContext
from database.database import (
    check_existing_meal_times,
    get_user_id_by_tg_user_id,
    get_user_timezone,
    update_breakfast_time_in_db,
    update_lunch_time_in_db,
    update_dinner_time_in_db,
    get_meal_status_for_today,
    get_meals_per_day,
    update_meal_status
)
from handlers.meal_schedule_handler import convert_to_utc
from aiogram.dispatcher import FSMContext
from states import UserData
from scheduler import add_daily_task, scheduler

from handlers.eat_handler.breakfast_handlers import start_breakfast
from handlers.eat_handler.lunch_handlers import start_lunch
from handlers.eat_handler.dinner_handlers import start_dinner
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger
import pytz


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class RegistrationCheckMiddleware(BaseMiddleware):
    def __init__(self, pool, allowed_commands=None):
        super().__init__()
        self.pool = pool
        self.allowed_commands = allowed_commands or []

    async def on_process_message(self, message: types.Message, data: dict):
        #logger.info(f"Получено сообщение: {message.text} от пользователя {message.from_user.id}")
        #logger.info(f"Команды для проверки: {self.allowed_commands}")

        if message.text in self.allowed_commands:
            user_id = message.from_user.id
            logger.info(f"Проверка регистрации для пользователя {user_id}")

            try:
                user_db_id = await get_user_id_by_tg_user_id(self.pool, user_id)
                logger.info(f"Получен user_db_id: {user_db_id}")

                is_registered = await check_existing_meal_times(self.pool, user_db_id)
                logger.info(f"Проверка регистрации: {is_registered}")

                if not is_registered:
                    await message.answer(
                        "Пожалуйста, завершите регистрацию, прежде чем использовать эту команду."
                    )
                    logger.info(f"Пользователь {user_id} не зарегистрирован, отмена обработки.")
                    raise CancelHandler()
                else:
                    logger.info(f"Пользователь {user_id} зарегистрирован.")
            except Exception as e:
                logger.error(f"Ошибка при проверке регистрации для пользователя {user_id}: {e}")
                raise CancelHandler()


async def handle_menu_command(message: types.Message, context: AppContext):
    user_id = message.from_user.id
    logging.info(f"Обработка команды /menu для пользователя с ID {user_id}.")

    try:
        user_db_id = await get_user_id_by_tg_user_id(context.pool, user_id)
        logging.debug(f"Получен user_db_id: {user_db_id}.")

        is_registered = await check_existing_meal_times(context.pool, user_db_id)
        logging.debug(f"Статус регистрации для user_db_id {user_db_id}: {is_registered}.")

        if not is_registered:
            await message.answer("Пожалуйста, завершите регистрацию, прежде чем использовать эту функцию.")
            logging.info(f"Пользователь с ID {user_id} не завершил регистрацию.")
            return

        # Получаем текущий статус приемов пищи
        meal_status = await get_meal_status_for_today(context.pool, user_db_id)
        logging.debug(f"Статус приемов пищи для user_db_id {user_db_id}: {meal_status}.")

        # Получаем количество приемов пищи в день
        meals_per_day = int(await get_meals_per_day(context.pool, user_db_id))
        logging.debug(f"Количество приемов пищи в день для user_db_id {user_db_id}: {meals_per_day}.")

        # Определяем, что предложить пользователю в зависимости от статуса приемов пищи и количества приемов пищи в день
        if meal_status.get("breakfast", 0) == 0:
            logging.info(f"Завтрак не был завершен для пользователя с ID {user_id}. Начинаем завтрак.")
            await start_breakfast(context.dispatcher, context.pool, user_db_id)
        elif meal_status.get("lunch", 0) == 0 and meals_per_day == 3:
            logging.info(f"Обед не был завершен и предусмотрено 3 приема пищи в день для пользователя с ID {user_id}. Начинаем обед.")
            await start_lunch(context.dispatcher, context.pool, user_db_id)
        elif meal_status.get("dinner", 0) == 0:
            logging.info(f"Ужин не был завершен для пользователя с ID {user_id}. Начинаем ужин.")
            await start_dinner(context.dispatcher, context.pool, user_db_id)
        elif meal_status.get("second_breakfast", 0) == 0 and meals_per_day == 4:
            logging.info(f"Второй завтрак не был завершен и предусмотрено 4 приема пищи в день для пользователя с ID {user_id}. Начинаем второй завтрак.")
        else:
            logging.info(f"Все приемы пищи на сегодня завершены для пользователя с ID {user_id}.")
            await message.answer("Вы уже завершили все приемы пищи на сегодня.")

    except Exception as e:
        logging.error(f"Ошибка при обработке команды /menu для пользователя с ID {user_id}: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")



def translate_meal_type(meal_type):
    meal_translations = {
        "завтрак": "breakfast",
        "обед": "lunch",
        "ужин": "dinner"
    }
    return meal_translations.get(meal_type.lower(), meal_type.lower())


async def handle_meal_time_update(message: types.Message, state: FSMContext, pool):
    user_id = message.from_user.id
    text = message.text.strip()
    logger.info(f"Обработка сообщения пользователя {user_id}: {text}")

    current_state = await state.get_state()
    logger.info(f"Текущее состояние для пользователя {user_id}: {current_state}")

    if current_state == UserData.waiting_for_meal_time.state:
        logger.info("Сообщение обрабатывается в состоянии ожидания времени")
        await message.answer("Пожалуйста, введите время в формате HH:MM.")
        return

    if text.lower() in ["завтрак", "ужин"]:
        await state.update_data(meal_type=text.capitalize())
        await state.set_state(UserData.waiting_for_meal_time)
        logger.info(f"Установлено состояние ожидания времени для {text.capitalize()}")
        await message.answer(
            f"Хорошо, давай поменяем время для {text.capitalize()}. Пожалуйста, отправь время в формате HH:MM.")
    elif text.lower() == "обед":
        user_db_id = await get_user_id_by_tg_user_id(pool, user_id)
        meals_per_day = await get_meals_per_day(pool, user_db_id)

        if meals_per_day == 3:
            await state.update_data(meal_type=text.capitalize())
            await state.set_state(UserData.waiting_for_meal_time)
            logger.info(f"Установлено состояние ожидания времени для Обед.")
            await message.answer(
                "Хорошо, давай поменяем время для обеда. Пожалуйста, отправь время в формате HH:MM.")
        else:
            await message.answer(
                "Вы не можете изменить время обеда, так как у вас предусмотрены только два приёма пищи в день.")
            logger.info(f"Пользователь {user_id} пытается изменить время обеда, хотя у него предусмотрено только два приёма пищи.")
    else:
        await message.answer("Пожалуйста, напишите 'Завтрак', 'Обед' или 'Ужин'.")
        logger.info("Сообщение не содержит ключевых слов. Запрос повторного ввода.")



async def process_meal_time(message: types.Message, state: FSMContext, context: AppContext):
    user_id = message.from_user.id
    time_str = message.text.strip()

    logger.info(f"Получено время от пользователя {user_id}: '{time_str}'")

    if 'спасибо' in time_str.lower():
        logger.info(f"Сообщение пользователя {user_id} содержит слово 'спасибо'. Игнорирование.")
        return

    current_state = await state.get_state()
    logger.info(f"Текущее состояние для пользователя {user_id}: {current_state}")

    if current_state != UserData.waiting_for_meal_time.state:
        logger.info(f"Сообщение пользователя {user_id} не обрабатывается в состоянии ожидания времени. Пропуск.")
        return

    if not validate_time_format(time_str):
        await message.answer("Пожалуйста, введите время в формате HH:MM.")
        logger.info(f"Введено некорректное время: '{time_str}'. Запрос повторного ввода.")
        return

    data = await state.get_data()
    meal_type = data.get("meal_type")
    logger.info(f"Тип приема пищи для обновления: {meal_type}")

    try:
        user_db_id = await get_user_id_by_tg_user_id(context.pool, user_id)
        logger.info(f"Получен user_db_id: {user_db_id}")

        timezone = await get_user_timezone(context.pool, user_db_id)
        logger.info(f"Часовой пояс пользователя {user_id}: {timezone}")

        meal_time_utc = convert_to_utc(time_str, timezone)
        meal_type_english = translate_meal_type(meal_type)

        # Обновление времени приема пищи в базе данных
        if meal_type == "Завтрак":
            await update_breakfast_time_in_db(context.pool, user_db_id, meal_time_utc)
        elif meal_type == "Обед":
            await update_lunch_time_in_db(context.pool, user_db_id, meal_time_utc)
        elif meal_type == "Ужин":
            await update_dinner_time_in_db(context.pool, user_db_id, meal_time_utc)
        else:
            logger.error(f"Неизвестный тип приема пищи: {meal_type}.")
            await message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
            return

        # Добавление новой задачи в планировщик
        await add_daily_task(context, user_db_id, meal_time_utc, meal_type_english)

        await message.answer(
            "Теперь вам доступна кнопка «Меню», она находится слева снизу и выделяется синим цветом ‼️\n\n"
            "1️⃣ Если вы захотите изменить время приема пищи, напишите мне кодовое слово \"Завтрак / Обед / Ужин\".\n\n"
            "2️⃣ Если вы захотите поесть раньше назначенного времени, нажмите «меню»."
        )

        await state.finish()
        logger.info(f"Обновление времени для {meal_type} завершено и состояние сброшено.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении времени для {meal_type}: {e}")
        await message.answer("Произошла ошибка при обновлении времени. Пожалуйста, попробуйте снова.")


async def handle_thank_you(message: types.Message):
    response_text = (
        "Большое спасибо за ваше сообщение! 😊 Мы всегда рады помочь. "
        "Желаем вам отличного дня!"
    )
    await message.reply(response_text)
    logger.info(f"Отправлено благодарственное сообщение пользователю {message.from_user.id}")



def validate_time_format(time_str):
    """Проверяет формат времени."""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False

async def handle_help_command(message: types.Message):
    """
    Обработчик команды /help. Отправляет сообщение с ссылкой на поддержку.
    """
    support_link = "https://t.me/vladimirriss"
    await message.answer(
        f"Если у вас возникли вопросы или нужна помощь, вы можете обратиться к нашему помощнику по этой ссылке: {support_link}"
    )


def register_handlers_with_middleware(context: AppContext):
    dp = context.dispatcher
    pool = context.pool

    # Регистрация Middleware
    registration_middleware = RegistrationCheckMiddleware(
        pool=context.pool,
        allowed_commands=['завтрак', 'обед', 'ужин', 'спасибо', 'благодарю', 'сяпки', 'help']
    )
    dp.middleware.setup(registration_middleware)

    # Регистрация обработчиков сообщений
    dp.register_message_handler(
        lambda message, state: handle_meal_time_update(message, state, context.pool),
        lambda message: any(
            keyword in message.text.lower() for keyword in ['завтрак', 'обед', 'ужин']),
        content_types=types.ContentTypes.TEXT
    )

    dp.register_message_handler(
        lambda message, state: process_meal_time(message, state, context),
        state=UserData.waiting_for_meal_time,
        content_types=types.ContentTypes.TEXT
    )

    dp.register_message_handler(
        handle_thank_you,
        lambda message: any(
            keyword in message.text.lower() for keyword in ['спасибо', 'благодарю', 'сяпки']),
        content_types=types.ContentTypes.TEXT
    )

    dp.register_message_handler(
        partial(handle_menu_command, context=context),  # Передаем контекст
        commands=['menu'],
        content_types=types.ContentTypes.TEXT
    )

    # Обработчик команды /help
    dp.register_message_handler(handle_help_command, commands=['help'])

