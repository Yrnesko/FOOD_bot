import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageCantBeEdited
from states import UserData
from menu.menu_messages import get_result_message, generate_data_confirmation_keyboard
from context import AppContext

logging.basicConfig(level=logging.INFO)

activity_level_display = {
    "1.2": "Низкий",
    "1.55": "Средний",
    "1.9": "Высокий"
}

async def show_user_data(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    logging.info("Displaying user data: %s", user_data)

    result_message = get_result_message(user_data, activity_level_display, user_data.get('meals_per_day'))

    try:
        sent_message = await message.edit_text(result_message, reply_markup=generate_data_confirmation_keyboard())
        await state.update_data(message_id=sent_message.message_id)
    except MessageCantBeEdited:
        logging.error("Message can't be edited. It might have been deleted or not accessible.")
        sent_message = await message.answer(result_message, reply_markup=generate_data_confirmation_keyboard())
        await state.update_data(message_id=sent_message.message_id)

    await state.set_state(UserData.confirming_data)
    logging.info("State changed to UserData.confirming_data")
    logging.info("Current state: %s", await state.get_state())

async def parameter_change_handler(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    logging.info("Parameter change requested: %s", data)

    state_data = await state.get_data()
    message_id = state_data.get('message_id')
    chat_id = callback_query.message.chat.id

    if data == "change_height":
        await state.set_state(UserData.changing_height)
        await callback_query.message.edit_text("Введите ваш новый рост (в см):")
    elif data == "change_weight":
        await state.set_state(UserData.changing_weight)
        await callback_query.message.edit_text("Введите ваш новый вес (в кг):")
    elif data == "change_age":
        await state.set_state(UserData.changing_age)
        await callback_query.message.edit_text("Введите ваш новый возраст:")
    elif data == "change_gender":
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(text="Мужской 🙋‍♂", callback_data="gender_male"),
            InlineKeyboardButton(text="Женский 🙋‍", callback_data="gender_female")
        )
        await callback_query.message.edit_text("Выберите ваш новый пол:", reply_markup=keyboard)
        await state.set_state(UserData.changing_gender)
    elif data == "change_activity_level":
        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton(text="Низкий", callback_data="activity_low"),
            InlineKeyboardButton(text="Средний", callback_data="activity_medium"),
            InlineKeyboardButton(text="Высокий", callback_data="activity_high")
        )
        await callback_query.message.edit_text("Выберите ваш новый уровень активности:", reply_markup=keyboard)
        await state.set_state(UserData.changing_activity_level)
    elif data == "change_meals_per_day":
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(text="2", callback_data="meals_2"),
            InlineKeyboardButton(text="3", callback_data="meals_3")
        )
        await callback_query.message.edit_text("Выберите новое количество приемов пищи в день:", reply_markup=keyboard)
        await state.set_state(UserData.changing_meals_per_day)

    logging.info("Current state: %s", await state.get_state())

async def change_height_handler(message: types.Message, state: FSMContext):
    try:
        height = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение роста.")
        return

    await state.update_data(height=height)
    logging.info("Height updated to %s", height)

    await update_user_data(message, state)

async def change_weight_handler(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение веса.")
        return

    await state.update_data(weight=weight)
    logging.info("Weight updated to %s", weight)

    await update_user_data(message, state)

async def change_age_handler(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение возраста.")
        return

    await state.update_data(age=age)
    logging.info("Age updated to %s", age)

    await update_user_data(message, state)

async def change_gender_handler(callback_query: types.CallbackQuery, state: FSMContext):
    gender = "мужской" if callback_query.data == "gender_male" else "женский"
    await state.update_data(gender=gender)
    logging.info("Gender updated to %s", gender)

    await update_user_data(callback_query.message, state)

async def change_activity_level_handler(callback_query: types.CallbackQuery, state: FSMContext):
    activity_level_mapping = {
        "activity_low": "1.2",
        "activity_medium": "1.55",
        "activity_high": "1.9"
    }

    activity_level = activity_level_mapping.get(callback_query.data)
    await state.update_data(activity_level=activity_level)
    logging.info("Activity level updated to %s", activity_level)

    await update_user_data(callback_query.message, state)

async def change_meals_per_day_handler(callback_query: types.CallbackQuery, state: FSMContext):
    meals_per_day = 2 if callback_query.data == "meals_2" else 3
    await state.update_data(meals_per_day=meals_per_day)
    logging.info("Meals per day updated to %s", meals_per_day)

    await update_user_data(callback_query.message, state)

async def update_user_data(message: types.Message, state: FSMContext):
    await show_user_data(message, state)

def register_change_data_handlers(context: AppContext):
    dp = context.dispatcher
    dp.register_callback_query_handler(parameter_change_handler, state=UserData.choosing_parameter_to_change)
    dp.register_message_handler(change_height_handler, state=UserData.changing_height)
    dp.register_message_handler(change_weight_handler, state=UserData.changing_weight)
    dp.register_message_handler(change_age_handler, state=UserData.changing_age)
    dp.register_callback_query_handler(change_gender_handler, state=UserData.changing_gender)
    dp.register_callback_query_handler(change_activity_level_handler, state=UserData.changing_activity_level)
    dp.register_callback_query_handler(change_meals_per_day_handler, state=UserData.changing_meals_per_day)
