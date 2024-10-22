import random
import aiomysql
from config import get_db_config
import pytz
from datetime import date
from decimal import Decimal
import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_pool():
    config = get_db_config()
    try:
        pool = await aiomysql.create_pool(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            db=config['database'],
            minsize=1,
            maxsize=100
        )
        return pool
    except KeyError as e:
        logging.error(f"Missing configuration key: {e}")
        raise
    except Exception as e:
        logging.error(f"Error creating database pool: {e}")
        raise


async def get_recipes(pool, meal_type, preparation_time):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            query = """
            SELECT * 
            FROM recipes 
            WHERE meal_type = %s 
              AND (preparation_time = %s OR 
                   (preparation_time = '30_to_60_minutes' AND %s IN ('30_to_60_minutes', 'more_than_60_minutes')) OR 
                   (preparation_time = 'more_than_60_minutes'))
            ORDER BY RAND() 
            LIMIT 2
            """
            await cursor.execute(query, (meal_type, preparation_time, preparation_time))
            recipes = await cursor.fetchall()
            return recipes


async def get_greeting(pool, meal_type):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            query = """
            SELECT greeting_text 
            FROM meal_greetings 
            WHERE meal_type = %s 
              AND greeting_type = 'greeting'
            """
            await cursor.execute(query, (meal_type,))
            greetings = await cursor.fetchall()
            if greetings:
                return random.choice(greetings)['greeting_text']
            else:
                return None


async def get_farewell(pool, meal_type):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            query = """
            SELECT greeting_text 
            FROM meal_greetings 
            WHERE meal_type = %s 
              AND greeting_type = 'farewell'
            """
            await cursor.execute(query, (meal_type,))

            # Извлекаем все прощальные сообщения для выбранного типа приема пищи
            farewells = await cursor.fetchall()

            # Прочитываем все оставшиеся результаты, чтобы избежать ошибок
            while await cursor.nextset():
                pass

            # Если список прощальных сообщений не пуст, выбираем случайное прощальное сообщение
            if farewells:
                return random.choice(farewells)['greeting_text']
            else:
                return None  # или любое другое значение, если прощальных сообщений не найдено


async def get_tg_user_id_by_user_id(pool, user_id: int) -> int:
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            query = """
            SELECT tg_user_id
            FROM users
            WHERE id = %s
            """
            await cursor.execute(query, (user_id,))

            # Получаем результат
            result = await cursor.fetchone()

            if result:
                return result['tg_user_id']
            else:
                return None


async def user_exists(pool, user_id):
    query = "SELECT COUNT(*) FROM users WHERE id = %s"
    try:
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, (user_id,))
                count = await cursor.fetchone()
                return count[0] > 0
    except aiomysql.MySQLError as err:
        logger.error(f"Ошибка при проверке существования пользователя: {err}")
        return False


async def update_calories(pool, user_id, calories):
    today = datetime.date.today()
    if not await user_exists(pool, user_id):
        logger.error(f"Пользователь с ID {user_id} не существует.")
        return None
    try:
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO user_calories (user_id, calories_consumed, date)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        calories_consumed = calories_consumed + VALUES(calories_consumed),
                        date = VALUES(date)
                    """, (user_id, calories, today)
                )
                await connection.commit()
                return True
    except aiomysql.MySQLError as err:
        logger.error(f"Ошибка базы данных при обновлении потребленных калорий: {err}")
        return None


async def update_calories_to_zero(pool, user_id, calories):
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                await cursor.execute(
                    """
                    INSERT INTO user_calories (user_id, calories_consumed)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE calories_consumed = %s
                    """, (user_id, calories)
                )
                await connection.commit()
                logger.info(f"Successfully updated calories for user ID {user_id}.")
                return True
            except aiomysql.MySQLError as err:
                logger.error(f"Ошибка базы данных при обновлении потребленных калорий: {err}")
                return None


async def get_calories_consumed(pool, user_id):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    SELECT calories_consumed
                    FROM user_calories
                    WHERE user_id = %s
                    """, (user_id,)
                )
                result = await cursor.fetchone()
                return result['calories_consumed'] if result else 0
            except aiomysql.Error as err:
                logger.error(f"Ошибка базы данных при получении потребленных калорий: {err}")
                return 0


async def get_calorie_norm(pool, user_id):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    SELECT calorie_norm
                    FROM users
                    WHERE id = %s
                    """, (user_id,)
                )
                result = await cursor.fetchone()

                if result:
                    return result['calorie_norm']
                else:
                    logger.warning(f"Не найдена норма калорий для пользователя с id {user_id}.")
                    return None
            except aiomysql.Error as err:
                logger.error(f"Ошибка базы данных при получении нормы калорий: {err}")
                return None


async def get_recipe_by_id(pool, recipe_id):
    try:
        async with pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    """
                    SELECT title, instructions, ingredients, calories, protein, fats, carbohydrates, image_url, preparation_time
                    FROM recipes
                    WHERE id = %s
                    """, (recipe_id,)
                )
                recipe = await cursor.fetchone()

                if not recipe:
                    logger.warning(f"Рецепт с ID {recipe_id} не найден.")
                    return None

                # Проверка формата данных (по необходимости)
                if any(key not in recipe for key in
                       ["title", "instructions", "ingredients", "calories", "protein", "fats", "carbohydrates",
                        "image_url", "preparation_time"]):
                    logger.error(f"Неправильный формат данных рецепта с ID {recipe_id}: {recipe}")
                    return None

                return recipe

    except aiomysql.Error as err:
        logger.error(f"Ошибка базы данных при получении рецепта: {err}")
        return None


async def get_user_id_by_tg_user_id(pool, tg_user_id: int):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                await cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE tg_user_id = %s
                    """, (tg_user_id,)
                )
                result = await cursor.fetchone()

                if result:
                    return result['id']
                else:
                    return None
            except aiomysql.Error as err:
                print(f"Ошибка базы данных: {err}")
                return None


async def get_meals_per_day(pool, user_id: int) -> int:
    logging.debug(f"Получение количества приемов пищи для пользователя с ID {user_id}.")

    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                query = """
                SELECT meals_per_day
                FROM users
                WHERE id = %s
                """
                logging.debug(f"Выполнение запроса: {query} с параметром {user_id}.")
                await cursor.execute(query, (user_id,))
                result = await cursor.fetchone()

                if result:
                    meals_per_day = result['meals_per_day']
                    logging.info(f"Количество приемов пищи для пользователя с ID {user_id}: {meals_per_day}.")
                    return meals_per_day
                else:
                    logging.warning(f"Пользователь с ID {user_id} не найден в базе данных.")
                    return None  # Возвращаем None, чтобы указать, что данных нет

            except aiomysql.Error as err:
                logging.error(
                    f"Ошибка базы данных при получении количества приемов пищи для пользователя с ID {user_id}: {err}")
                return None  # Возвращаем None в случае ошибки


async def check_existing_meal_times(pool, user_id: int) -> bool:
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                logging.info(f"Проверка существующих времен приема пищи для пользователя с ID {user_id}")

                # Выполняем запрос для подсчета количества записей
                await cursor.execute("SELECT COUNT(*) as count FROM meal_schedules WHERE user_id = %s", (user_id,))
                result = await cursor.fetchone()

                if result:
                    logging.info(f"Результат запроса для пользователя {user_id}: {result}")
                    found_meals = result['count'] > 0

                    if found_meals:
                        logging.info(f"Для пользователя {user_id} найдены времена приема пищи (количество: {result['count']})")
                    else:
                        logging.info(f"Для пользователя {user_id} не найдены времена приема пищи.")

                    return found_meals
                else:
                    logging.warning(f"Пустой результат для пользователя {user_id}.")
                    return False

            except aiomysql.Error as err:
                logging.error(f"Ошибка базы данных при проверке времен приема пищи для пользователя {user_id}: {err}")
                return False



async def update_breakfast_time_in_db(pool, user_id, new_breakfast_time):
    """Обновляет время завтрака пользователя в базе данных асинхронно."""
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                query = '''
                    UPDATE meal_schedules
                    SET breakfast_time = %s
                    WHERE user_id = %s
                '''
                await cursor.execute(query, (new_breakfast_time, user_id))
                await connection.commit()
                logging.info(f"Updated breakfast time for user {user_id} to {new_breakfast_time}.")
            except aiomysql.Error as err:
                await connection.rollback()
                logging.error(f"Error updating breakfast time: {err}")


async def update_lunch_time_in_db(pool, user_id, new_lunch_time):

    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                query = '''
                    UPDATE meal_schedules
                    SET lunch_time = %s
                    WHERE user_id = %s
                '''
                await cursor.execute(query, (new_lunch_time, user_id))
                await connection.commit()
            except aiomysql.Error as err:
                await connection.rollback()
                logging.error(f"Error updating lunch time: {err}")


async def update_dinner_time_in_db(pool, user_id, new_dinner_time):
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                query = '''
                    UPDATE meal_schedules
                    SET dinner_time = %s
                    WHERE user_id = %s
                '''
                await cursor.execute(query, (new_dinner_time, user_id))
                await connection.commit()
            except aiomysql.Error as err:
                await connection.rollback()
                logging.error(f"Error updating dinner time: {err}")


async def get_user_timezone(pool, user_id):
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            try:
                query = '''
                    SELECT user_timezone
                    FROM meal_schedules
                    WHERE user_id = %s
                '''
                await cursor.execute(query, (user_id,))
                result = await cursor.fetchone()

                if result:
                    return result['user_timezone']
                else:
                    logging.info(f"No timezone found for user_id {user_id}.")
                    return None
            except aiomysql.Error as err:
                logging.error(f"Error retrieving user timezone: {err}")
                return None


def convert_timezone_to_offset(timezone_str):
    try:
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        offset_minutes = int(now.utcoffset().total_seconds() / 60)
        sign = '+' if offset_minutes >= 0 else '-'
        offset_minutes = abs(offset_minutes)
        hours, minutes = divmod(offset_minutes, 60)
        return f"{sign}{hours:02}:{minutes:02}"
    except pytz.UnknownTimeZoneError:
        print(f"Unknown timezone: {timezone_str}")
        return None


async def get_meal_status_for_today(pool, user_db_id: int):
    today = date.today()
    query = """
    SELECT breakfast_flag, second_breakfast_flag, lunch_flag, dinner_flag
    FROM user_calories
    WHERE user_id = %s AND date = %s;
    """
    try:
        async with pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, (user_db_id, today))
                result = await cursor.fetchone()

                if result:
                    return {
                        "breakfast": result.get('breakfast_flag', 0),
                        "second_breakfast": result.get('second_breakfast_flag', 0),
                        "lunch": result.get('lunch_flag', 0),
                        "dinner": result.get('dinner_flag', 0)
                    }
                else:
                    return {
                        "breakfast": 0,
                        "second_breakfast": 0,
                        "lunch": 0,
                        "dinner": 0
                    }
    except aiomysql.Error as err:
        logging.error(f"Ошибка при выполнении SQL-запроса для user_id {user_db_id}: {err}")
        return {
            "breakfast": 0,
            "second_breakfast": 0,
            "lunch": 0,
            "dinner": 0
        }






async def update_meal_status(pool, user_db_id: int, meal_type: str, status: int):
    meal_column_map = {
        "breakfast": "breakfast_flag",
        "lunch": "lunch_flag",
        "dinner": "dinner_flag"
    }

    meal_type = meal_type.lower()
    column_name = meal_column_map.get(meal_type)

    if not column_name:
        logging.error(f"Неправильный тип приема пищи: {meal_type}")
        raise ValueError(f"Неправильный тип приема пищи: {meal_type}")

    # SQL запрос для проверки даты
    check_date_query = "SELECT date FROM user_calories WHERE user_id = %s"

    # SQL запрос для обнуления всех флагов
    reset_flags_query = """
        INSERT INTO user_calories (user_id, date, breakfast_flag, lunch_flag, dinner_flag)
        VALUES (%s, CURDATE(), 0, 0, 0)
        ON DUPLICATE KEY UPDATE breakfast_flag = 0, lunch_flag = 0, dinner_flag = 0;
    """

    # SQL запрос для обновления конкретного флага
    update_flag_query = f"""
        INSERT INTO user_calories (user_id, date, {column_name})
        VALUES (%s, CURDATE(), %s)
        ON DUPLICATE KEY UPDATE {column_name} = %s;
    """

    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                # Проверка даты
                await cursor.execute(check_date_query, (user_db_id,))
                result = await cursor.fetchone()
                current_date = datetime.date.today()

                if result:
                    stored_date = result[0]  # Предполагается, что result[0] уже типа datetime.date
                    if stored_date != current_date:
                        # Если дата не соответствует сегодняшней, обнуляем все флаги
                        await cursor.execute(reset_flags_query, (user_db_id,))
                        await connection.commit()

                # Обновление флага для конкретного приема пищи
                status = 1 if status else 0
                await cursor.execute(update_flag_query, (user_db_id, status, status))
                await connection.commit()

            except Exception as e:
                logging.error(f"Ошибка при обновлении статуса приема пищи: {e}")


async def subtract_calories(pool, user_id, recipe_calories):
    try:
        async with pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                # Приведение калорий к float, если это необходимо
                if isinstance(recipe_calories, Decimal):
                    recipe_calories = float(recipe_calories)

                # Уменьшаем количество потребленных калорий
                today = datetime.date.today()

                await cursor.execute(
                    """
                    UPDATE user_calories
                    SET calories_consumed = calories_consumed - %s
                    WHERE user_id = %s AND date = %s
                    """, (recipe_calories, user_id, today)
                )
                await connection.commit()
                #logger.info(f"Successfully subtracted calories for user ID {user_id}.")
                return True

    except aiomysql.MySQLError as err:
        logger.error(f"Ошибка базы данных при вычитании калорий: {err}")
        return None







