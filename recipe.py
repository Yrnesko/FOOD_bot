import aiomysql
import logging
import random
from database.database import get_calorie_norm, get_meals_per_day

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import decimal

# Преобразование decimal.Decimal в float
def decimal_to_float(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value

async def fetch_recipe(meal_type, prep_times, user_id, pool):
    recipes = []
    try:
        # Получаем норму калорий для пользователя
        calorie_norm = await get_calorie_norm(pool, user_id)
        calorie_norm = decimal_to_float(calorie_norm)  # Преобразование к float

        if calorie_norm is None:
            logger.warning(f"Не удалось получить норму калорий для пользователя {user_id}.")
            return recipes

        meals_per_day = await get_meals_per_day(pool, user_id)
        if isinstance(meals_per_day, str):
            try:
                meals_per_day = int(meals_per_day)
            except ValueError:
                logger.error(f"Не удалось преобразовать количество приемов пищи в число: {meals_per_day}")
                return recipes

        if meals_per_day <= 0:
            logger.error(f"Количество приемов пищи должно быть положительным числом, но получено: {meals_per_day}")
            return recipes

        # Расчет калорий на один прием пищи в зависимости от типа пищи
        if meal_type == "snack":
            total_calories_for_snack = calorie_norm * 0.33  # 33% от нормы на перекус
            min_calories = total_calories_for_snack * 0.9
            max_calories = total_calories_for_snack * 1.1
        else:
            # Для других типов пищи
            if meals_per_day == 2:
                calorie_per_meal = calorie_norm * 0.3  # 30% на завтрак или обед
            elif meals_per_day == 3:
                if meal_type == "breakfast":
                    calorie_per_meal = calorie_norm * 0.33  # 33% на завтрак
                elif meal_type == "lunch":
                    calorie_per_meal = calorie_norm * 0.33  # 33% на обед
                elif meal_type == "dinner":
                    calorie_per_meal = calorie_norm * 0.33  # 33% на ужин
                else:
                    logger.error(f"Неизвестный тип приема пищи: {meal_type}")
                    return recipes

            min_calories = calorie_per_meal * 0.9
            max_calories = calorie_per_meal * 1.1

        min_calories = decimal_to_float(min_calories)  # Преобразование к float
        max_calories = decimal_to_float(max_calories)  # Преобразование к float

        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if prep_times:  # Если указано время приготовления
                    placeholders = ', '.join(['%s'] * len(prep_times))
                    query = f"""
                        SELECT title, instructions, ingredients, calories, protein, fats, carbohydrates, image_url, id
                        FROM recipes
                        WHERE meal_type = %s AND preparation_time IN ({placeholders}) AND calories BETWEEN %s AND %s
                    """
                    params = [meal_type] + prep_times + [min_calories, max_calories]
                else:  # Если время приготовления не указано
                    query = f"""
                        SELECT title, instructions, ingredients, calories, protein, fats, carbohydrates, image_url, id
                        FROM recipes
                        WHERE meal_type = %s AND calories BETWEEN %s AND %s
                    """
                    params = [meal_type, min_calories, max_calories]

                await cursor.execute(query, params)
                recipes = await cursor.fetchall()

                # Логирование количества рецептов после основного запроса
                logger.info(f"Количество рецептов после основного запроса: {len(recipes)}")

                if not recipes:
                    # Если основной запрос не вернул данных, пробуем запасной запрос
                    query = f"""
                        SELECT title, instructions, ingredients, calories, protein, fats, carbohydrates, image_url, id
                        FROM recipes
                        WHERE meal_type = %s AND calories <= %s
                    """
                    params = [meal_type, max_calories]
                    await cursor.execute(query, params)
                    recipes = await cursor.fetchall()

                    # Логирование количества рецептов после запасного запроса
                    logger.info(f"Количество рецептов после запасного запроса: {len(recipes)}")

                if recipes and meal_type == "snack":
                    selected_recipes = []
                    total_calories = 0

                    # Перемешиваем рецепты для случайного выбора
                    random.shuffle(recipes)

                    # Подбираем рецепты, чтобы суммарные калории были близки к total_calories_for_snack
                    for recipe in recipes:
                        if len(selected_recipes) < 3 and total_calories + recipe['calories'] <= max_calories:
                            selected_recipes.append(recipe)
                            total_calories += recipe['calories']
                            if total_calories >= min_calories:
                                break

                    # Если не удалось набрать минимальное количество калорий, добавляем еще рецепты
                    if total_calories < min_calories:
                        for recipe in recipes:
                            if recipe not in selected_recipes and len(selected_recipes) < 3 and total_calories + recipe['calories'] <= max_calories:
                                selected_recipes.append(recipe)
                                total_calories += recipe['calories']
                                if total_calories >= min_calories:
                                    break

                    recipes = selected_recipes

                    # Логирование количества выбранных перекусов
                    logger.info(f"Количество выбранных перекусов: {len(recipes)}")

    except aiomysql.MySQLError as err:
        logger.error(f"Ошибка базы данных: {err}")
    return recipes

