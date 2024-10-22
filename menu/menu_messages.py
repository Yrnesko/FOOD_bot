from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiomysql import MySQLError
import logging
from states import UserData
from context import AppContext
from middlewares.manager import apply_free_trial
from payments import create_payment_link
from aiomysql import DictCursor
from database.database import get_user_id_by_tg_user_id, check_existing_meal_times
from handlers.meal_schedule_handler import choose_timezone
import asyncio


activity_level_display = {
    "1.2": "Низкий",
    "1.55": "Средний",
    "1.9": "Высокий"
}

async def change_data_handler(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info("Change data requested by user: %s", callback_query.from_user.id)
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="Изменить рост", callback_data="change_height"),
        InlineKeyboardButton(text="Изменить вес", callback_data="change_weight"),
        InlineKeyboardButton(text="Изменить возраст", callback_data="change_age"),
        InlineKeyboardButton(text="Изменить пол", callback_data="change_gender"),
        InlineKeyboardButton(text="Изменить уровень активности", callback_data="change_activity_level"),
        InlineKeyboardButton(text="Изменить количество приемов пищи", callback_data="change_meals_per_day")
    )

    # Обновляем сообщение с параметрами для изменения
    await callback_query.message.edit_text(
        "Выберите параметр, который хотите изменить:",
        reply_markup=keyboard
    )
    await state.set_state(UserData.choosing_parameter_to_change)
    logging.info("State changed to UserData.choosing_parameter_to_change")
    logging.info("Current state: %s", await state.get_state())


def generate_data_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="Изменить данные", callback_data="change_data"),
        InlineKeyboardButton(text="Продолжить", callback_data="confirm_data")
    )
    return keyboard


def get_result_message(user_data, activity_level_display, meals_per_day):
    activity_level_display_value = activity_level_display.get(str(user_data['activity_level']), "Неизвестно")

    return (
        f"Ваши данные:\n"
        f"Рост: {user_data['height']} см\n"
        f"Вес: {user_data['weight']} кг\n"
        f"Возраст: {user_data['age']} лет\n"
        f"Пол: {user_data['gender']}\n"
        f"Уровень активности: {activity_level_display_value}\n"
        f"Количество приемов пищи: {meals_per_day}\n"
        "Пожалуйста, проверьте введенные данные."
    )


async def confirm_data_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    user_data = await state.get_data()
    user_id = callback_query.from_user.id
    try:
        try:
            activity_level = float(user_data['activity_level'])
            gender = user_data['gender']
            height = float(user_data['height'])
            weight = float(user_data['weight'])
            age = int(user_data['age'])
            meals_per_day = str(user_data['meals_per_day'])
        except ValueError as e:
            logging.error(f"Data conversion error for user {user_id}: {e}")
            return

        gender_factor = 5 if gender == 'мужской' else -161
        calorie_norm = (10 * weight + 6.25 * height - 5 * age + gender_factor) * activity_level * 0.8
        logging.info(f"Calculated calorie norm: {calorie_norm:.2f}")

        async with context.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                try:
                    # Обновление данных пользователя
                    logging.info(f"Executing SQL query for user {user_id}")
                    await cursor.execute(
                        """
                        UPDATE users 
                        SET 
                            height = %s, 
                            weight = %s, 
                            gender = %s, 
                            age = %s,
                            activity_level = %s, 
                            meals_per_day = %s,
                            calorie_norm = %s,
                            is_registered = 1,
                            free_trial_used = FALSE
                        WHERE 
                            tg_user_id = %s
                        """,
                        (
                            height,
                            weight,
                            gender,
                            age,
                            activity_level,
                            meals_per_day,
                            calorie_norm,
                            user_id  # Используем правильный идентификатор
                        )
                    )
                    await connection.commit()
                    logging.info(f"User {user_id} data confirmed and updated.")

                except MySQLError as e:
                    await connection.rollback()
                    logging.error(f"Database error during transaction for user {user_id}: {e}")
                    await callback_query.message.edit_text(
                        "Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.")
                    return

        # Отправка результата
        result_message = (
            f"Ваша суточная норма калорий составляет {calorie_norm:.2f} ккал.\n"
            "Теперь давайте подберем вам питание."
        )

    except Exception as e:
        logging.error(f"Unexpected error for user {user_id}: {e}")
        result_message = "Произошла неожиданная ошибка. Пожалуйста, попробуйте позже."

    await callback_query.message.edit_text(result_message)

    subscription_keyboard = generate_subscription_keyboard()
    menu_message = "Выберите один из вариантов ниже:"
    await callback_query.message.answer(menu_message, reply_markup=subscription_keyboard)
    await state.set_state(UserData.managing_subscription)

    logging.info(f"User {user_id} state set to {UserData.managing_subscription.state}")

    # Проверка, что состояние обновлено
    current_state = await state.get_state()
    logging.info(f"Текущее состояние после обновления для пользователя {user_id}: {current_state}")



def generate_subscription_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="Получить бесплатный день подписки", callback_data="free_trial"),
        InlineKeyboardButton(text="3 дня подписки", callback_data="subscription_3_days"),
        InlineKeyboardButton(text="30 дней подписки", callback_data="subscription_30_days")
    )
    return keyboard

def generate_subscription_keyboard_trial_used():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="3 дня подписки", callback_data="subscription_3_days"),
        InlineKeyboardButton(text="30 дней подписки", callback_data="subscription_30_days")
    )
    return keyboard


async def subscription_callback_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    user_id = callback_query.from_user.id
    callback_data = callback_query.data
    logging.info(f"Получены данные callback: {callback_data} от пользователя: {user_id}")

    pool = context.pool
    logging.info(f"context.pool: {context.pool}")
    max_retries = 5  # Максимальное количество попыток
    retry_delay = 0.1  # Задержка между попытками в секундах
    retries = 0

    while retries < max_retries:
        async with pool.acquire() as connection:
            async with connection.cursor(DictCursor) as cursor:
                try:
                    # Выполняем SQL запрос для извлечения всех полей пользователя
                    await cursor.execute("""
                            SELECT *
                            FROM users
                            WHERE tg_user_id = %s
                        """, (user_id,))

                    # Получаем результат
                    user_info = await cursor.fetchone()

                    if user_info:
                        # Логируем информацию о пользователе
                        logging.info(f"User Info for ID {user_id}: {user_info}")
                        break  # Выходим из цикла, если пользователь найден
                    else:
                        retries += 1
                        logging.warning(f"User with ID {user_id} not found. Attempt {retries} of {max_retries}.")
                        await asyncio.sleep(retry_delay)  # Ожидаем перед повтором

                except Exception as e:
                    logging.error(f"Database error: {e}")
                    await callback_query.answer("Ошибка базы данных.")
                    return

    if retries == max_retries:
        logging.error(f"Max retries reached. User with ID {user_id} not found.")
        await callback_query.answer("Пользователь не найден.")
        return  # Прерываем выполнение, если пользователь не найден после всех попыток

    # Дальнейшая логика обработки подписок
    if callback_data in ["free_trial", "subscription_3_days", "subscription_30_days"]:
        if callback_data == "free_trial":
            logging.info(f"Пользователь {user_id} запрашивает бесплатный пробный день.")
            success = await apply_free_trial(pool, user_id)
            logging.info(f"Результат активации бесплатного пробного дня для пользователя {user_id}: {success}")

            if not success:
                logging.info(f"Пользователь {user_id} уже использовал бесплатный пробный день.")
                await callback_query.message.edit_text(
                    "Вы уже использовали бесплатный день подписки.\n\n"
                    "Пожалуйста, выберите опцию подписки:",
                    reply_markup=generate_subscription_keyboard_trial_used()
                )
                await state.set_state(UserData.managing_subscription)
                return

            await callback_query.message.edit_text(
                "Бесплатный день подписки активирован! 🎉\n"
                "Вы можете продолжать пользоваться ботом. Приятного использования!"
            )
            await state.finish()


        elif callback_data == "subscription_3_days":
            logging.info(f"Пользователь {user_id} запрашивает подписку на 3 дня.")
            payment = await create_payment_link(amount=300, description="Подписка на 3 дня", user_id=user_id)
            keyboard = InlineKeyboardMarkup(row_width=1)
            payment_button = InlineKeyboardButton(text="Оплатить подписку на 3 дня",
                                                  url=payment.confirmation.confirmation_url)
            status_button = InlineKeyboardButton(text="Проверить статус оплаты",
                                                 callback_data=f"check_payment_{payment.id}")
            back_button = InlineKeyboardButton(text="Назад", callback_data="back_to_subscription")
            keyboard.add(payment_button, status_button, back_button)
            # Отправляем сообщение с кнопками
            await callback_query.message.edit_text(
                "Для оплаты подписки на 3 дня, нажмите на кнопку ниже. После оплаты нажмите 'Проверить статус оплаты':",
                reply_markup=keyboard
            ) 
            return
        elif callback_data == "subscription_30_days":
            logging.info(f"Пользователь {user_id} запрашивает подписку на 30 дней.")
            payment = await create_payment_link(amount=990, description="Подписка на 30 дней", user_id=user_id)
            # Создание клавиатуры с кнопками для оплаты, проверки статуса и возврата
            keyboard = InlineKeyboardMarkup(row_width=1)
            payment_button = InlineKeyboardButton(text="Оплатить подписку на 30 дней",
                                                  url=payment.confirmation.confirmation_url)
            status_button = InlineKeyboardButton(text="Проверить статус оплаты",
                                                 callback_data=f"check_payment_{payment.id}")
            back_button = InlineKeyboardButton(text="Назад", callback_data="back_to_subscription")
            keyboard.add(payment_button, status_button, back_button)
            await callback_query.message.edit_text(
                "Для оплаты подписки на 30 дней, нажмите на кнопку ниже. После оплаты нажмите 'Проверить статус оплаты':",
                reply_markup=keyboard
            )
            return
    user_id_by_tg = await get_user_id_by_tg_user_id(pool, user_id)
    if user_id_by_tg:
        existing_meal_times = await check_existing_meal_times(pool, user_id_by_tg)
        logging.info(f"Существующие данные времени приема пищи для TG ID {user_id_by_tg}: {existing_meal_times}")

        if existing_meal_times:
            logging.info(f"У пользователя {user_id} уже есть данные времени приема пищи.")
            await callback_query.message.edit_text(
                    "Ваша подписка активирована! 🎉\nСпасибо за оформление подписки.\n"
                    "Вы можете продолжать пользоваться ботом. Приятного использования!"
                )
        else:
            logging.info(f"У пользователя {user_id} нет данных времени приема пищи. Переходим к сбору времени приема пищи.")
            await choose_timezone(callback_query.message, state)
    else:
        logging.warning(f"Не удалось получить ID пользователя {user_id}. Дальнейшая обработка невозможна.")

async def handle_back_to_subscription(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    logging.info(f"Пользователь {user_id} возвращается к выбору подписки.")

    # Отправляем сообщение с клавиатурой для выбора подписки
    await callback_query.message.edit_text(
        "Пожалуйста, выберите опцию подписки:",
        reply_markup=generate_subscription_keyboard()
    )
    await state.set_state(UserData.managing_subscription)


def register_menu_messages_handlers(context: AppContext):
    dp = context.dispatcher
    dp.register_callback_query_handler(
        lambda cbq, state: confirm_data_handler(cbq, state, context),
        state=UserData.confirming_data,
        text="confirm_data"
    )
    dp.register_callback_query_handler(change_data_handler, state=UserData.confirming_data, text="change_data")
    dp.register_callback_query_handler(lambda cbq, state: subscription_callback_handler(cbq, state, context),
                                           state=UserData.managing_subscription, text_startswith="free_trial")
    dp.register_callback_query_handler(lambda cbq, state: subscription_callback_handler(cbq, state, context),
                                           state=UserData.managing_subscription, text_startswith="subscription_3_days")
    dp.register_callback_query_handler(lambda cbq, state: subscription_callback_handler(cbq, state, context),
                                       state=UserData.managing_subscription, text_startswith="subscription_30_days")
    dp.register_callback_query_handler(handle_back_to_subscription, lambda c: c.data == "back_to_subscription", state= UserData.managing_subscription)


