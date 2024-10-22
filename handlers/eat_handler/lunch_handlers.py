import random
import logging
from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.database import (get_greeting, get_farewell,
                               get_tg_user_id_by_user_id, get_user_id_by_tg_user_id,
                               get_recipe_by_id, update_calories,
                               subtract_calories, get_meal_status_for_today
                               )
from recipe import fetch_recipe
from context import AppContext
from decimal import Decimal
from database.function import ask_if_ate
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_lunch(dispatcher: Dispatcher, pool, user_id: int):
    try:
        tg_user_id = await get_tg_user_id_by_user_id(pool, user_id)
        logger.info(f"tg_user_id получен: {tg_user_id}")

        if not tg_user_id:
            raise ValueError("tg_user_id is empty")

        #logger.info(f"Начало процесса завтрака для пользователя с ID: {user_id}")

        # Получаем приветственное сообщение для завтрака
        greeting_text = await get_greeting(pool, "lunch")
        if greeting_text:
            #logger.info(f"Отправка приветствия для завтрака пользователю с ID {user_id}: {greeting_text}")

            await dispatcher.bot.send_photo(
                tg_user_id,
                photo="https://i.imgur.com/b9ChIFy.png",
                caption=greeting_text
            )
        else:
            logger.warning(f"Приветственное сообщение для завтрака не найдено")

        # Отправляем кнопки выбора времени приготовления
        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton(text="15-20 минут", callback_data="lunch_up_to_30_minutes"),
            InlineKeyboardButton(text="30-60 минут", callback_data="lunch_30_to_60_minutes"),
            InlineKeyboardButton(text="Более 60 минут", callback_data="lunch_more_than_60_minutes")
        )
        #logger.info(f"Отправка опций времени приготовления пользователю с ID {user_id}")
        await dispatcher.bot.send_message(tg_user_id, "Сколько у вас времени на приготовление обеда?",
                                          reply_markup=keyboard)
        logger.info("Опции времени приготовления отправлены.")
    except Exception as e:
        logger.error(f"Ошибка в start_lunch: {e}")


# Обработчик для выбора времени приготовления завтрака
async def choose_prep_time_lunch(callback_query: types.CallbackQuery, pool):
    try:
        #logger.info(f"Получен callback_query: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        prep_time = callback_query.data
        logger.info(f"Пользователь с ID {user_id} выбрал время приготовления: {prep_time}")

        # Приводим данные из callback_data в нужный формат
        prep_time_map = {
            "lunch_up_to_30_minutes": ["up_to_30_minutes"],
            "lunch_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "lunch_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("lunch", prep_times, user_id, pool)
        #logger.info(f"Получение рецептов для пользователя с ID {user_id} с временем приготовления: {prep_times}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"lunch_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"lunch_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="lunch_back_to_prep_time"))
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        logger.info(f"Отправка рецептов пользователю с ID {user_id}")
        await callback_query.message.edit_text("Выберите рецепт из предложенных:", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в choose_prep_time_lunch: {e}")


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
                                 callback_data=f"lunch_no_ingredients:{recipe_id}:lunch_{prep_time}")
        )

        # Отправка сообщения с рецептом
        await callback_query.message.delete()
        if image_url:
            await callback_query.message.answer_photo(photo=image_url, caption=message_text, reply_markup=keyboard,
                                                      parse_mode='Markdown')
            farewell_text = await get_farewell(pool, "lunch")
            if farewell_text:
                await callback_query.message.answer(farewell_text)
            else:
                logger.warning(f"Прощальное сообщение для завтрака не найдено")
        else:
            await callback_query.message.answer(message_text, reply_markup=keyboard, parse_mode='Markdown')

        meal_status = await get_meal_status_for_today(pool, user_id)

        # Проверяем завтрак
        if meal_status['lunch'] == 0:
            await ask_if_ate(tg_user_id, 'lunch', context,calories)
        # Обновляем количество потребленных калорий
        await update_calories(pool, user_id, calories)

        logger.info(f"Обновлено количество калорий для пользователя с ID {user_id}: {calories} ккал")

    except Exception as e:
        logger.error(f"Ошибка в send_recipe_and_update_calories: {e}")
async def reroll_recipes(callback_query: types.CallbackQuery, pool):
    try:
        logger.info(f"Получен callback_query для reroll: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        _, prep_time = callback_query.data.split(":")

        prep_time_map = {
            "lunch_up_to_30_minutes": ["up_to_30_minutes"],
            "lunch_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "lunch_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("lunch", prep_times, user_id, pool)
        #logger.info(f"Получение рецептов для пользователя с ID {user_id} с временем приготовления: {prep_times}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"lunch_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"lunch_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="lunch_back_to_prep_time"))
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
            "lunch_up_to_30_minutes": ["up_to_30_minutes"],
            "lunch_30_to_60_minutes": ["up_to_30_minutes", "30_to_60_minutes"],
            "lunch_more_than_60_minutes": ["up_to_30_minutes", "30_to_60_minutes", "more_than_60_minutes"]
        }
        prep_times = prep_time_map.get(prep_time, None)
        if not prep_times:
            logger.warning(f"Неверное значение времени приготовления: {prep_time}")
            return

        # Получаем рецепты с учетом времени приготовления
        recipes = await fetch_recipe("lunch", prep_times, user_id, pool)
        logger.info(f"Новые рецепты: {recipes}")

        # Исключаем оригинальный рецепт из нового списка
        recipes = [recipe for recipe in recipes if recipe['id'] != original_recipe_id]

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"lunch_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data=f"lunch_reroll:{prep_time}")
        )
        buttons.append(
            InlineKeyboardButton(text="Вернуться к выбору времени", callback_data="lunch_back_to_prep_time"))
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




async def back_to_prep_time(callback_query: types.CallbackQuery, pool):
    try:
        logger.info(f"Пользователь {callback_query.from_user.id} возвращается к выбору времени приготовления обеда.")

        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton(text="15-20 минут", callback_data="lunch_up_to_30_minutes"),
            InlineKeyboardButton(text="30-60 минут", callback_data="lunch_30_to_60_minutes"),
            InlineKeyboardButton(text="Более 60 минут", callback_data="lunch_more_than_60_minutes")
        )
        await callback_query.message.edit_text("Сколько у вас времени на приготовление обеда?", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка в back_to_prep_time: {e}")

def register_lunch_handlers(context: AppContext):
    try:
        dp = context.dispatcher
        pool = context.pool
        dp.register_callback_query_handler(lambda c: choose_prep_time_lunch(c, pool), lambda c: c.data in [
            "lunch_up_to_30_minutes",
            "lunch_30_to_60_minutes",
            "lunch_more_than_60_minutes"
        ])
        dp.register_callback_query_handler(lambda c: send_recipe_and_update_calories(c, context),
                                           lambda c: c.data.startswith("lunch_recipe:"))
        dp.register_callback_query_handler(lambda c: reroll_recipes(c, pool),
                                           lambda c: c.data.startswith("lunch_reroll:"))
        dp.register_callback_query_handler(lambda c: handle_no_ingredients(c, pool),
                                           lambda c: c.data.startswith("lunch_no_ingredients:"))

        # Регистрация обработчика для дополнительного завтрака

        dp.register_callback_query_handler(lambda c: back_to_prep_time(c, pool),
                                           lambda c: c.data == "lunch_back_to_prep_time")
    except Exception as e:
        logger.error(f"Ошибка в register_lunch_handlers: {e}")
