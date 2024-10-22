import logging
from datetime import datetime, timedelta
from aiomysql import DictCursor
from database.database import get_user_id_by_tg_user_id
import asyncio


async def activate_subscription(pool, user_tg_id: int, days: int):
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                user_id = await get_user_id_by_tg_user_id(pool, user_tg_id)
                # Проверяем существование пользователя
                await cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                user_exists = await cursor.fetchone()

                if not user_exists:
                    logging.error(f"User with ID {user_id} does not exist.")
                    return False

                # Вычисляем дату окончания подписки
                end_date = datetime.now() + timedelta(days=days)

                # Вставляем или обновляем запись о подписке
                await cursor.execute("""
                    INSERT INTO subscriptions (user_id, start_date, end_date, is_active)
                    VALUES (%s, NOW(), %s, TRUE)
                    ON DUPLICATE KEY UPDATE 
                        start_date = VALUES(start_date), 
                        end_date = VALUES(end_date), 
                        is_active = VALUES(is_active)
                """, (user_id, end_date))

                # Коммит изменений
                await connection.commit()

                # Логируем успешную активацию подписки
                logging.info(f"Subscription activated for user {user_id} until {end_date}.")

                # Обновляем статус задач для пользователя
                await update_task_status(connection, user_id, True)

                return True

            except Exception as e:
                # Логируем ошибку, если произошла проблема с базой данных
                logging.error(f"Database error for user {user_id}: {e}")
                return False


async def update_task_status(connection, user_id: int, is_active: bool):
    async with connection.cursor() as cursor:
        try:
            # Обновляем флаг is_active для всех задач пользователя
            await cursor.execute("""
                UPDATE scheduled_tasks
                SET is_active = %s
                WHERE user_id = %s
            """, (is_active, user_id))

            # Коммит изменений
            await connection.commit()

            # Логируем успешное обновление задач
            logging.info(f"Updated task statuses for user {user_id} to {'active' if is_active else 'inactive'}.")

        except Exception as e:
            # Логируем ошибку, если произошла проблема с базой данных
            logging.error(f"Error updating task statuses for user {user_id}: {e}")


async def apply_free_trial(pool, user_id: int):
    max_retries = 5  # Максимальное количество попыток
    retry_delay = 0.1  # Задержка между попытками в секундах
    retries = 0
    user = None  # Переменная для хранения информации о пользователе

    while retries < max_retries:
        async with pool.acquire() as connection:
            async with connection.cursor(DictCursor) as cursor:
                try:
                    logging.info(f"функция получила юзера = == = = = = = {user_id} ")

                    # Проверяем наличие пользователя в таблице users
                    await cursor.execute("""
                        SELECT id, free_trial_used 
                        FROM users 
                        WHERE tg_user_id = %s
                    """, (user_id,))
                    user = await cursor.fetchone()

                    if user:
                        logging.info(f"User {user_id} found in users table with free_trial_used = {user['free_trial_used']}")
                        break  # Если пользователь найден, выходим из цикла
                    else:
                        retries += 1
                        logging.warning(f"User {user_id} not found in users table. Attempt {retries} of {max_retries}.")
                        await asyncio.sleep(retry_delay)  # Ожидаем перед следующей попыткой

                except Exception as e:
                    logging.error(f"Database error for user {user_id}: {e}")
                    return False

    if not user:
        logging.error(f"User {user_id} not found after {max_retries} attempts.")
        return False

    # Проверяем, использовал ли пользователь бесплатный пробный день
    if user['free_trial_used']:
        logging.info(f"User {user_id} has already used the free trial day.")
        return False

    try:
        async with pool.acquire() as connection:
            async with connection.cursor(DictCursor) as cursor:
                # Вставляем или обновляем запись в таблице subscriptions
                await cursor.execute("""
                    INSERT INTO subscriptions (user_id, start_date, end_date, is_active)
                    VALUES (%s, NOW(), DATE_ADD(NOW(), INTERVAL 1 DAY), TRUE)
                    AS new_data
                    ON DUPLICATE KEY UPDATE 
                        start_date = new_data.start_date, 
                        end_date = new_data.end_date, 
                        is_active = new_data.is_active
                """, (user['id'],))

                # Обновляем флаг free_trial_used в таблице users
                await cursor.execute("""
                    UPDATE users 
                    SET free_trial_used = TRUE
                    WHERE id = %s
                """, (user['id'],))

                # Подтверждаем изменения в транзакции
                await connection.commit()

                logging.info(f"Free trial day activated for user {user_id}.")
                return True

    except Exception as e:
        logging.error(f"Database error during trial activation for user {user_id}: {e}")
        return False
