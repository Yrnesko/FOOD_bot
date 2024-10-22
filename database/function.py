from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import types
import logging
from database.database import (
    get_user_id_by_tg_user_id,
    update_meal_status, update_calories
)
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger
import pytz
from functools import partial
from context import AppContext
import importlib

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ask_if_ate(tg_user_id, meal_type: str, context: AppContext, calories):
    dispatcher = context.dispatcher
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text=f"Да, спасибо!", callback_data=f"ate_now_{meal_type}:{calories}"),
        InlineKeyboardButton(text="Я еще не поел(а) ", callback_data="just_looking")
    )
    # Отправляем сообщение с кнопками
    message = await dispatcher.bot.send_message(
        tg_user_id, "Скажите мне, пожалуйста, поели вы уже или нет?", reply_markup=keyboard
    )
    # Сохраняем идентификатор сообщения для последующего удаления
    return message.message_id



async def handle_ate_now(callback_query: types.CallbackQuery, meal_type: str, pool, dispatcher, is_scheduled_call=False):
    scheduler = importlib.import_module('scheduler').scheduler
    user_id = callback_query.from_user.id
    user_db_id = await get_user_id_by_tg_user_id(pool, user_id)

    tz = pytz.timezone('UTC')
    now = datetime.now(tz)
    callback_data = callback_query.data
    try:
        # Пытаемся получить данные из callback_data
        parts = callback_data.split(":")
        if len(parts) != 2:
            raise ValueError("Неверный формат callback_data")

        meal_type_from_data, calories_str = parts
        calories = float(calories_str)

        # Обновляем количество потребленных калорий
        await update_calories(pool, user_db_id, calories)
    except ValueError as e:
        logger.error(f"Ошибка при обработке данных калорий: {callback_data} - {e}")
        return

    task_name = f"{meal_type}_notification_{user_db_id}"

    # Удаление существующей задачи только для указанного типа еды
    existing_job = scheduler.get_job(task_name)
    if existing_job:
        logger.info(f"Задача {task_name} существует. Удаление задачи.")
        scheduler.remove_job(task_name)
    else:
        logger.info(f"Задача {task_name} не найдена в планировщике.")

    await update_meal_status(pool, user_db_id, meal_type, 1)
    logger.info(f"Статус приема пищи {meal_type} обновлен как завершенный для пользователя {user_db_id}.")

    logger.info(f"Процедура приема пищи запущена для пользователя {user_db_id}.")

    try:
        next_day = now + timedelta(days=1)
        if existing_job:
            trigger = existing_job.trigger
            if isinstance(trigger, CronTrigger):
                previous_fire_time = existing_job.next_run_time
                if previous_fire_time.tzinfo is None:
                    previous_fire_time = tz.localize(previous_fire_time)
                next_fire_time = trigger.get_next_fire_time(previous_fire_time, now)
                if next_fire_time:
                    hour = next_fire_time.hour
                    minute = next_fire_time.minute
                else:
                    hour = minute = None
            else:
                hour = minute = None
        else:
            hour = minute = None

        if hour is not None and minute is not None:
            # Динамически импортируем нужные модули и функции
            module_name = f"handlers.eat_handler.{meal_type}_handlers"
            handler_module = importlib.import_module(module_name)
            handler_function = getattr(handler_module, f"start_{meal_type}")

            if not scheduler.get_job(f"{meal_type}_notification_{user_db_id}"):
                scheduler.add_job(
                    handler_function,
                    'cron',
                    hour=hour,
                    minute=minute,
                    id=f"{meal_type}_notification_{user_db_id}",
                    args=[dispatcher, pool, user_db_id]
                )
                logger.info(f"Запланирована новая задача {task_name} на следующий день.")
            else:
                logger.info(f"Задача {task_name} уже существует. Не добавляем новую.")
        else:
            logger.error(f"Не удалось получить время для задачи {task_name}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении новой задачи: {e}")

    # Удаление сообщения после обработки, если это не автоматический вызов
    if not is_scheduled_call:
        await callback_query.message.delete()

    await callback_query.answer("Спасибо! Статус обновлен.")


async def handle_just_looking(callback_query: types.CallbackQuery):
    # Удаление сообщения после обработки
    # await callback_query.message.delete()
    await callback_query.answer("Окей, просто посмотрите. Если что, дайте знать!")


async def handle_second_ate_now(callback_query: types.CallbackQuery, pool):
    user_id = callback_query.from_user.id
    callback_data = callback_query.data
    user_db_id = get_user_id_by_tg_user_id(pool, user_id)

    try:
        meal_type, calories = callback_data.split(":")
        calories = int(calories)
        # Обновляем количество потребленных калорий
        await update_calories(pool, user_db_id, calories)
    except ValueError:
        logger.error(f"Ошибка при обработке данных калорий: {callback_data}")

def register_handlers_function(context: AppContext):
    dp = context.dispatcher
    pool = context.pool

    dp.register_callback_query_handler(
        partial(handle_ate_now, meal_type="breakfast", pool=pool, dispatcher=dp),
        lambda c: c.data.startswith("ate_now_breakfast:")
    )

    dp.register_callback_query_handler(
        partial(handle_ate_now, meal_type="lunch", pool=pool, dispatcher=dp),
        lambda c: c.data.startswith("ate_now_lunch:")
    )

    dp.register_callback_query_handler(
        partial(handle_ate_now, meal_type="dinner", pool=pool, dispatcher=dp),
        lambda c: c.data.startswith("ate_now_dinner:")
    )

    dp.register_callback_query_handler(
        handle_just_looking,
        text="just_looking"
    )
    dp.register_callback_query_handler(
        lambda c: handle_second_ate_now(c, pool),
        lambda c: c.data.startswith("ate_now_second_breakfast:")
    )

