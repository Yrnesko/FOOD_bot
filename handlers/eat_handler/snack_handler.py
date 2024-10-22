import random
import logging
from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.database import (get_greeting, get_farewell,
                               get_tg_user_id_by_user_id, get_user_id_by_tg_user_id,
                               get_recipe_by_id, update_calories,
                               subtract_calories)
from recipe import fetch_recipe
from context import AppContext
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_snack(dispatcher: Dispatcher, pool, user_id: int):
    try:
        tg_user_id = await get_tg_user_id_by_user_id(pool, user_id)
        logger.info(f"tg_user_id получен: {tg_user_id}")

        if not tg_user_id:
            raise ValueError("tg_user_id is empty")

        logger.info(f"Начало процесса перекуса для пользователя с ID: {user_id}")
        greeting_text = await get_greeting(pool, "snack")
        if greeting_text:
            logger.info(f"Отправка приветствия для перекуса пользователю с ID {user_id}: {greeting_text}")

            await dispatcher.bot.send_message(
                tg_user_id, greeting_text
            )
        else:
            logger.warning(f"Приветственное сообщение для перекуса не найдено")

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("snack", [], user_id, pool)
        #logger.info(f"Получение рецептов для пользователя с ID {user_id}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"snack_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data="snack_choose_recipe")
        )
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        logger.info(f"Отправка рецептов пользователю с ID {user_id}")
        await dispatcher.bot.send_message(tg_user_id, "Выберите рецепт перекуса:", reply_markup=keyboard)
        logger.info("Рецепты отправлены.")
    except Exception as e:
        logger.error(f"Ошибка в start_snack: {e}")

async def send_recipe_and_update_calories(callback_query: types.CallbackQuery, context: AppContext):
    try:
        #logger.info(f"Получен callback_query для рецепта: {callback_query.data}")
        pool = context.pool
        dispatcher = context.dispatcher

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
                         "image_url"]
        if not all(key in recipe for key in required_keys):
            logger.error(
                f"Некорректный формат данных рецепта с ID {recipe_id}. Отсутствуют ключи: {[key for key in required_keys if key not in recipe]}")
            return

        title = recipe["title"]
        instructions = recipe.get("instructions", "")
        ingredients = recipe.get("ingredients", "")
        calories = recipe.get("calories")
        protein = recipe.get("protein")
        fats = recipe.get("fats")
        carbohydrates = recipe.get("carbohydrates")
        image_url = recipe.get("image_url", "")

        # Формируем сообщение с учетом отсутствующих данных
        message_text = f"*{title}*\n\n"
        if instructions:
            message_text += f"{instructions}\n\n"
        if ingredients:
            message_text += f"*Ингредиенты:*\n{ingredients}\n\n"
        if calories is not None:
            message_text += f"*Калории:* {calories} ккал\n"
        if protein is not None:
            message_text += f"*Белки:* {protein} г\n"
        if fats is not None:
            message_text += f"*Жиры:* {fats} г\n"
        if carbohydrates is not None:
            message_text += f"*Углеводы:* {carbohydrates} г\n"

        # Добавляем кнопку "У меня нет нужных ингредиентов"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(text="У меня нет нужных ингредиентов",
                                 callback_data=f"snack_no_ingredients:{recipe_id}")
        )

        # Отправка сообщения с рецептом
        await callback_query.message.delete()
        if image_url:
            await callback_query.message.answer_photo(photo=image_url, caption=message_text, reply_markup=keyboard,
                                                      parse_mode='Markdown')
            farewell_text = await get_farewell(pool, "snack")
            if farewell_text:
                await callback_query.message.answer(farewell_text)
            else:
                logger.warning(f"Прощальное сообщение для перекуса не найдено")
        else:
            await callback_query.message.answer(message_text, reply_markup=keyboard, parse_mode='Markdown')

        # Обновляем количество потребленных калорий
        await update_calories(pool, user_id, calories)
    except Exception as e:
        logger.error(f"Ошибка в send_recipe_and_update_calories: {e}")


async def handle_no_ingredients(callback_query: types.CallbackQuery, pool):
    try:
        #logger.info(f"Получен callback_query для отсутствующих ингредиентов: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)
        _, original_recipe_id = callback_query.data.split(":")

        # Получаем оригинальный рецепт, чтобы исключить его из нового списка
        original_recipe = await get_recipe_by_id(pool, original_recipe_id)
        logger.info(f"Оригинальный рецепт: {original_recipe}")

        if not original_recipe:
            logger.warning(f"Оригинальный рецепт с ID {original_recipe_id} не найден.")
            return

        recipe_calories = original_recipe.get('calories', 0)

        # Приведение к типу float для вычитания
        if isinstance(recipe_calories, Decimal):
            recipe_calories = float(recipe_calories)

        # Вычитаем калории старого рецепта
        await subtract_calories(pool, user_id, recipe_calories)

        # Получаем новые рецепты
        recipes = await fetch_recipe("snack", [], user_id, pool)
        logger.info(f"Новые рецепты: {recipes}")

        # Исключаем оригинальный рецепт из нового списка
        recipes = [recipe for recipe in recipes if recipe['id'] != original_recipe_id]

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"snack_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data="snack_choose_recipe")
        )
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        # Удаление последних двух сообщений
        try:
            await callback_query.bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
            await callback_query.bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id + 1)
            #logger.info("Удалены последние два сообщения.")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщений: {e}")

        # Отправляем новое сообщение с предложением новых рецептов
        await callback_query.message.answer("Выберите новый рецепт перекуса:", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в handle_no_ingredients: {e}")


async def reroll_recipes(callback_query: types.CallbackQuery, pool):
    try:
        logger.info(f"Получен callback_query для перезапроса рецептов: {callback_query.data}")
        user_id = await get_user_id_by_tg_user_id(pool, callback_query.from_user.id)

        # Используем функцию fetch_recipe для получения рецептов
        recipes = await fetch_recipe("snack", [], user_id, pool)
        logger.info(f"Получение рецептов для пользователя с ID {user_id}")

        # Выбираем случайные 4 рецепта из полученных
        random_recipes = random.sample(recipes, min(4, len(recipes)))

        # Создаем кнопки для выбора рецептов
        buttons = [
            InlineKeyboardButton(
                text=recipe['title'],
                callback_data=f"snack_recipe:{recipe['id']}"
            ) for recipe in random_recipes
        ]
        buttons.append(
            InlineKeyboardButton(text="Еще рецепты", callback_data="snack_choose_recipe")
        )
        keyboard = InlineKeyboardMarkup(row_width=1).add(*buttons)

        # Проверка на изменения перед редактированием
        if callback_query.message.text != "Выберите рецепт из предложенных:" or callback_query.message.reply_markup != keyboard:
            logger.info(f"Отправка новых рецептов пользователю с ID {user_id}")
            await callback_query.message.edit_text("Выберите рецепт из предложенных:", reply_markup=keyboard)
        else:
            logger.info("Сообщение и клавиатура не изменились, пропускаем edit_text.")

    except Exception as e:
        logger.error(f"Ошибка в reroll_recipes: {e}")


def register_snack_handlers(context: AppContext):
    dp = context.dispatcher
    pool = context.pool
    dp.register_callback_query_handler(lambda c: send_recipe_and_update_calories(c, context),
                                       lambda c: c.data.startswith("snack_recipe:"))
    dp.register_callback_query_handler(lambda c: reroll_recipes(c, pool),
                                       lambda c: c.data.startswith("snack_choose_recipe"))
    dp.register_callback_query_handler(lambda c: handle_no_ingredients(c, pool),
                                       lambda c: c.data.startswith("snack_no_ingredients:"))
