import random
import logging
from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.database import (get_greeting, get_farewell,
                               get_tg_user_id_by_user_id, get_user_id_by_tg_user_id,
                               get_recipe_by_id, update_calories,
                               subtract_calories, get_meals_per_day,
                               get_meal_status_for_today
                               )
from recipe import fetch_recipe
from context import AppContext
from handlers.eat_handler.snack_handler import start_snack
import asyncio
from decimal import Decimal
from database.function import ask_if_ate

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_breakfast(dispatcher: Dispatcher, pool, user_id: int):
    try:
        tg_user_id = await get_tg_user_id_by_user_id(pool, user_id)
        logger.info(f"tg_user_id получен: {tg_user_id}")

        if not tg_user_id:
            raise ValueError("tg_user_id is empty")

        #logger.info(f"Начало процесса завтрака для пользователя с ID: {user_id}")

        # Получаем приветственное сообщение для завтрака
        greeting_text = await get_greeting(pool, "breakfast")
        if greeting_text:
            #logger.info(f"Отправка приветствия для завтрака пользователю с ID {user_id}: {greeting_text}")

            await dispatcher.bot.send_photo(
                tg_user_id,
                photo="https://i.imgur.com/aRC0Dag.jpeg",
                caption=greeting_text
            )
        else:
            logger.warning(f"Приветственное сообщение для завтрака не найдено")

        # Отправляем кнопки выбора времени приготовления
        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton(text="15-20 минут", callback_data="breakfast_up_to_30_minutes"),
            InlineKeyboardButton(text="30-60 минут", callback_data="breakfast_30_to_60_minutes"),
            InlineKeyboardButton(text="Более 60 минут", callback_data="breakfast_more_than_60_minutes")
        )
        #logger.info(f"Отправка опций времени приготовления пользователю с ID {user_id}")
        await dispatcher.bot.send_message(tg_user_id, "Сколько у вас времени на приготовление завтрака?",
                                          reply_markup=keyboard)
        logger.info("Опции времени приготовления отправлены.")
    except Exception as e:
        logger.error(f"Ошибка в start_breakfast: {e}")


# Обработчик для выбора времени приготовления завтрака
async def choose_prep_time_breakfast(callback_query: types.CallbackQuery, pool):
    try:
        #logger.info(f"Получен callback_query: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        prep_time = callback_query.data
        logger.info(f"Пользователь с ID {user_id} выбрал время приготовления: {prep_time}")

        # Приводим данные из callback_data в нужный формат
        prep_time_map = {
            "breakfast_up_to_30_minutes": ["up_to_30_minutes"],
            "breakfast_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "breakfast_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("breakfast", prep_times, user_id, pool)
        #logger.info(f"Получение рецептов для пользователя с ID {user_id} с временем приготовления: {prep_times}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"breakfast_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"breakfast_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="breakfast_back_to_prep_time"))
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        logger.info(f"Отправка рецептов пользователю с ID {user_id}")
        await callback_query.message.edit_text("Выберите рецепт из предложенных:", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в choose_prep_time_breakfast: {e}")


# Обработчик для отправки рецепта и обновления информации о калориях
async def send_recipe_and_update_calories(callback_query: types.CallbackQuery, context: AppContext):
    try:
        tg_user_id = callback_query.from_user.id
        pool = context.pool

        # Получаем user_id из callback_query
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        recipe_id = callback_query.data.split(":")[1]
        #logger.info(f"Пользователь с ID {user_id} выбрал рецепт с ID {recipe_id}")

        # Получаем рецепт по ID
        recipe = await get_recipe_by_id(pool, recipe_id)

        # Проверка на None
        if not recipe:
            logger.warning(f"Рецепт с ID {recipe_id} не найден.")
            return

        # Проверяем, что результат функции get_recipe_by_id содержит все необходимые данные
        required_keys = ["title", "instructions", "ingredients", "calories", "protein", "fats", "carbohydrates",
                         "image_url", "preparation_time"]
        if not all(key in recipe for key in required_keys):
            logger.error(
                f"Некорректный формат данных рецепта с ID {recipe_id}. Отсутствуют ключи: {[key for key in required_keys if key not in recipe]}")
            return

        # Извлечение данных из словаря
        title = recipe["title"]
        instructions = recipe["instructions"]
        ingredients = recipe["ingredients"]
        calories = recipe["calories"]
        protein = recipe["protein"]
        fats = recipe["fats"]
        carbohydrates = recipe["carbohydrates"]
        image_url = recipe["image_url"]
        prep_time = recipe["preparation_time"]

        # Создание сообщения
        message_text = f"*{title}*\n\n"
        if instructions:
            message_text += f"{instructions}\n\n"
        message_text += f"*Ингредиенты:*\n{ingredients}\n\n"
        message_text += f"*Калории:* {calories} ккал\n"
        message_text += f"*Белки:* {protein} г\n"
        message_text += f"*Жиры:* {fats} г\n"
        message_text += f"*Углеводы:* {carbohydrates} г"

        # Добавляем кнопку "У меня нет нужных ингредиентов"
        keyboard = InlineKeyboardMarkup(row_width=1)
        # Правильное формирование callback_data с использованием времени приготовления
        keyboard.add(
            InlineKeyboardButton(text="У меня нет нужных ингредиентов",
                                 callback_data=f"breakfast_no_ingredients:{recipe_id}:breakfast_{prep_time}")
        )

        # Отправка сообщения с рецептом
        await callback_query.message.delete()
        if image_url:
            await callback_query.message.answer_photo(photo=image_url, caption=message_text, reply_markup=keyboard,
                                                      parse_mode='Markdown')
            farewell_text = await get_farewell(pool, "breakfast")
            if farewell_text:
                await callback_query.message.answer(farewell_text)
            else:
                logger.warning(f"Прощальное сообщение для завтрака не найдено")
        else:
            await callback_query.message.answer(message_text, reply_markup=keyboard, parse_mode='Markdown')

        meal_status = await get_meal_status_for_today(pool, user_id)

        # Проверяем завтрак
        if meal_status['breakfast'] == 0:
            await ask_if_ate(tg_user_id, 'breakfast', context, calories)
        else:
            # Проверяем, был ли выбран второй завтрак
            second_breakfast_chosen = await context.get_second_breakfast_chosen(user_id)
            if not second_breakfast_chosen:
                await ask_if_ate(tg_user_id, 'second_breakfast', context, calories)



        logger.info(f"Обновлено количество калорий для пользователя с ID {user_id}: {calories} ккал")

        # Проверяем количество приемов пищи у пользователя
        tg_user_id = await get_tg_user_id_by_user_id(pool, user_id)
        meals_count = int(await get_meals_per_day(pool, user_id))

        if meals_count == 2:
            await asyncio.sleep(180)  # 1800 секунд = 30 минут
            await offer_additional_breakfast_or_snack(tg_user_id, user_id, context)

    except Exception as e:
        logger.error(f"Ошибка в send_recipe_and_update_calories: {e}")


async def reroll_recipes(callback_query: types.CallbackQuery, pool):
    try:
        logger.info(f"Получен callback_query для reroll: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        _, prep_time = callback_query.data.split(":")

        prep_time_map = {
            "breakfast_up_to_30_minutes": ["up_to_30_minutes"],
            "breakfast_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "breakfast_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("breakfast", prep_times, user_id, pool)
        #logger.info(f"Получение рецептов для пользователя с ID {user_id} с временем приготовления: {prep_times}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"breakfast_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"breakfast_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="breakfast_back_to_prep_time"))
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        # Проверка на изменения перед редактированием
        if callback_query.message.text != "Выберите рецепт из предложенных:" or callback_query.message.reply_markup != keyboard:
            logger.info(f"Отправка новых рецептов пользователю с ID {user_id}")
            await callback_query.message.edit_text("Выберите рецепт из предложенных:", reply_markup=keyboard)
        else:
            logger.info("Сообщение и клавиатура не изменились, пропускаем edit_text.")

    except Exception as e:
        logger.error(f"Ошибка в reroll_recipes: {e}")


async def handle_no_ingredients(callback_query: types.CallbackQuery, pool):
    try:
        #logger.info(f"Получен callback_query для отсутствующих ингредиентов: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        _, original_recipe_id, prep_time = callback_query.data.split(":")

        # Получаем оригинальный рецепт, чтобы исключить его из нового списка
        original_recipe = await get_recipe_by_id(pool, original_recipe_id)
        #logger.info(f"Оригинальный рецепт: {original_recipe}")

        if not original_recipe:
            logger.warning(f"Оригинальный рецепт с ID {original_recipe_id} не найден.")
            return

        recipe_calories = original_recipe.get('calories', 0)

        # Приведение к типу float для вычитания
        if isinstance(recipe_calories, Decimal):
            recipe_calories = float(recipe_calories)

        # Вычитаем калории старого рецепта
        await subtract_calories(pool, user_id, recipe_calories)

        # Получаем новое предложение рецептов
        prep_time_map = {
            "breakfast_up_to_30_minutes": ["up_to_30_minutes"],
            "breakfast_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "breakfast_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Получаем рецепты с учетом времени приготовления
        recipes = await fetch_recipe("breakfast", prep_times, user_id, pool)
        logger.info(f"Новые рецепты: {recipes}")

        # Исключаем оригинальный рецепт из нового списка
        recipes = [recipe for recipe in recipes if recipe['id'] != original_recipe_id]

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"breakfast_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"breakfast_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="breakfast_back_to_prep_time"))
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        # Удаление последних двух сообщений
        try:
            await callback_query.bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
            await callback_query.bot.delete_message(callback_query.message.chat.id,
                                                    callback_query.message.message_id + 1)
            # logger.info("Удалены последние два сообщения.")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщений: {e}")
        # Отправляем новое сообщение с предложением новых рецептов
        await callback_query.message.answer("Выберите рецепт из предложенных:", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в handle_no_ingredients: {e}")


async def handle_extra_breakfast(callback_query: types.CallbackQuery, context: AppContext):
    try:
        user_id = await get_user_id_by_tg_user_id(context.pool, callback_query.from_user.id)

        # Удаление предыдущего сообщения
        if callback_query.message:
            await callback_query.message.delete()

        # Добавляем логику для дополнительного завтрака
        await start_breakfast(context.dispatcher, context.pool, user_id)

        # Обновляем состояние выбора второго завтрака в AppContext
        await context.set_second_breakfast_chosen(user_id, True)

        is_chosen = await context.get_second_breakfast_chosen(user_id)
        if is_chosen:
            logger.info(f"Состояние выбора второго завтрака для пользователя с ID {user_id} успешно обновлено.")
        else:
            logger.warning(f"Не удалось обновить состояние выбора второго завтрака для пользователя с ID {user_id}.")

    except Exception as e:
        logger.error(f"Ошибка в handle_extra_breakfast: {e}")


async def handle_extra_snack(callback_query: types.CallbackQuery, context: AppContext):
    try:
        user_id = await get_user_id_by_tg_user_id(context.pool, callback_query.from_user.id)

        # Удаление предыдущего сообщения
        if callback_query.message:
            await callback_query.message.delete()

        # Добавляем логику для дополнительного завтрака
        await start_snack(context.dispatcher, context.pool, user_id)
    except Exception as e:
        logger.error(f"Ошибка в handle_extra_snack: {e}")


async def offer_additional_breakfast_or_snack(tg_user_id, user_id, context: AppContext):
    try:
        dispatcher = context.dispatcher
        chosen = await context.get_second_breakfast_chosen(user_id)
        if chosen:
            logger.info(f"Пользователь с ID {user_id} уже выбрал второй завтрак, перекус не предлагается.")
            return
        # Сообщение пользователю
        message_text = (
            "К сожалению, у вас не получится добрать нужный каллораж без перекусов 😔\n\n"
            "Но не расстраивайтесь, они у нас безумно вкусные 😋\n\n"
            "Хотите попробовать?"
        )

        # Создаем кнопки
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(text="Выбрать перекус", callback_data="choose_snack"),
            InlineKeyboardButton(text="Дополнительный завтрак", callback_data="extra_breakfast")
        )

        # Отправляем сообщение с кнопками
        await dispatcher.bot.send_message(tg_user_id, message_text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в offer_additional_breakfast_or_snack: {e}")


async def back_to_prep_time(callback_query: types.CallbackQuery, pool):
    try:
        logger.info(f"Пользователь {callback_query.from_user.id} возвращается к выбору времени приготовления ужина.")

        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton(text="15-20 минут", callback_data="breakfast_up_to_30_minutes"),
            InlineKeyboardButton(text="30-60 минут", callback_data="breakfast_30_to_60_minutes"),
            InlineKeyboardButton(text="Более 60 минут", callback_data="breakfast_more_than_60_minutes")
        )
        await callback_query.message.edit_text("Сколько у вас времени на приготовление ужина?", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка в back_to_prep_time: {e}")


def register_breakfast_handlers(context: AppContext):
    try:
        dp = context.dispatcher
        pool = context.pool
        dp.register_callback_query_handler(lambda c: choose_prep_time_breakfast(c, pool), lambda c: c.data in [
            "breakfast_up_to_30_minutes",
            "breakfast_30_to_60_minutes",
            "breakfast_more_than_60_minutes"
        ])
        dp.register_callback_query_handler(lambda c: send_recipe_and_update_calories(c, context),
                                           lambda c: c.data.startswith("breakfast_recipe:"))
        dp.register_callback_query_handler(lambda c: reroll_recipes(c, pool),
                                           lambda c: c.data.startswith("breakfast_reroll:"))
        dp.register_callback_query_handler(lambda c: handle_no_ingredients(c, pool),
                                           lambda c: c.data.startswith("breakfast_no_ingredients:"))

        # Регистрация обработчика для дополнительного завтрака
        dp.register_callback_query_handler(
            lambda c: asyncio.create_task(handle_extra_breakfast(c, context)),
            lambda c: c.data == "extra_breakfast"
        )
        dp.register_callback_query_handler(lambda c: handle_extra_snack(c, context),
                                           lambda c: c.data == "choose_snack")
        dp.register_callback_query_handler(lambda c: back_to_prep_time(c, pool),
                                           lambda c: c.data == "breakfast_back_to_prep_time")
    except Exception as e:
        logger.error(f"Ошибка в register_breakfast_handlers: {e}")
