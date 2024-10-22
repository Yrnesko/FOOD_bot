import uuid
import logging
from aiogram import types
from yookassa import Configuration, Payment
from context import AppContext
from middlewares.manager import activate_subscription
from functools import partial
from aiogram.dispatcher import FSMContext
from states import UserData
from database.database import get_user_id_by_tg_user_id, check_existing_meal_times
from handlers.meal_schedule_handler import choose_timezone


# Инициализация ЮKassa
SHOP_ID = "437684"
API_KEY = "live_aYLw_tfLcD7mDaPVfctHRvZhMX52kagUMDYrK6A3wtw"

# Настройка конфигурации ЮKassa
Configuration.account_id = SHOP_ID
Configuration.secret_key = API_KEY


async def create_payment_link(amount, description, user_id):
    """
    Генерация платежа через ЮKassa
    """
    order_id = str(uuid.uuid4())

    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/testForALLOnlyme_bot"
        },
        "description": description,
        "metadata": {
            "order_id": order_id,
            "user_id": user_id
        },
        "receipt": {
            "customer": {
                "full_name": "Иван Иванов",
                "email": "example@example.com"
            },
            "items": [
                {
                    "description": description,
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service"
                }
            ]
        }
    }

    logging.info(f"Отправка данных платежа: {payment_data}")

    try:
        # Создание платежа через ЮKassa
        payment = Payment.create(payment_data)

        logging.info(f"Создан платеж: {payment.id}, confirmation_url: {payment.confirmation.confirmation_url}")

        return payment

    except Exception as e:
        logging.error(f"Ошибка при создании платежа: {str(e)}")
        raise


async def check_payment_status_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    logging.info(f"Начало проверки статуса оплаты для callback_query: {callback_query.data}")
    pool = context.pool
    user_id = callback_query.from_user.id

    try:
        payment_id = callback_query.data.split("_")[2]
        logging.info(f"Проверка статуса оплаты для платежа: {payment_id}")

        payment = Payment.find_one(payment_id)
        logging.info(f"Получен статус платежа: {payment.status}")

        # Для проверки кода предоставляем подписку при любом статусе, кроме явно исключенных
        if payment.status in ["succeeded", "waiting_for_capture"]:
            # Активируем подписку даже при статусе waiting_for_capture для проверки
            await activate_subscription(context.pool, payment.metadata["user_id"], 3)
            await callback_query.message.edit_text("Оплата успешно завершена! Ваша подписка активирована.")

            # Проверка существующих данных времени приема пищи
            user_id_by_tg = await get_user_id_by_tg_user_id(pool, user_id)
            logging.info(f"Получен ID для пользователя {user_id}: {user_id_by_tg}")

            existing_meal_times = await check_existing_meal_times(pool, user_id_by_tg)
            logging.info(f"Существующие данные времени приема пищи для TG ID {user_id_by_tg}: {existing_meal_times}")

            if existing_meal_times:
                logging.info(f"У пользователя {user_id} уже есть данные времени приема пищи.")
                await callback_query.message.edit_text(
                    "Ваша подписка активирована! 🎉\nСпасибо за оформление подписки.\n"
                    "Вы можете продолжать пользоваться ботом. Приятного использования!"
                )
            else:
                logging.info(
                    f"У пользователя {user_id} нет данных времени приема пищи. Переходим к сбору времени приема пищи.")
                await choose_timezone(callback_query.message, state)

        else:
            logging.warning(f"Платёж {payment_id} не прошёл. Статус: {payment.status}")
            await callback_query.message.answer("Платёж не прошёл. Пожалуйста, попробуйте снова.")

    except Exception as e:
        logging.error(f"Ошибка при проверке статуса оплаты: {str(e)}")
        await callback_query.message.answer(
            "Произошла ошибка при проверке статуса оплаты. Пожалуйста, попробуйте снова.")





# Регистрация обработчика
def register_payment_handlers(context: AppContext):
    dp = context.dispatcher

    # Регистрация обработчика с передачей контекста
    dp.register_callback_query_handler(
        partial(check_payment_status_handler, context=context),  # Передача контекста с использованием partial
        lambda c: c.data and c.data.startswith("check_payment_"),
        state=UserData.managing_subscription
    )

