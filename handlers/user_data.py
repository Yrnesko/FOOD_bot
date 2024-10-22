import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import types
from aiogram.dispatcher import FSMContext
from states import UserData
from menu.menu_messages import generate_data_confirmation_keyboard, get_result_message
from context import AppContext

# Configure logging
logging.basicConfig(level=logging.INFO)

async def height_handler(message: types.Message, state: FSMContext, context: AppContext):
    try:
        height = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение роста (например, 175.5).")
        return

    await state.update_data(height=height)
    await message.answer(
        "Принято!\n\n"
        "А теперь мне нужно узнать Ваш вес (в кг)?"
    )
    await state.set_state(UserData.waiting_for_weight)

async def weight_handler(message: types.Message, state: FSMContext, context: AppContext):
    try:
        weight = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение веса (например, 63.2).")
        return

    await state.update_data(weight=weight)
    await message.answer("Сколько вам лет?")
    await state.set_state(UserData.waiting_for_age)

async def age_handler(message: types.Message, state: FSMContext, context: AppContext):
    try:
        age = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное значение возраста (например, 25).")
        return

    await state.update_data(age=age)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="Мужской 🙋‍♂️", callback_data="gender_male"),
        InlineKeyboardButton(text="Женский 🙋‍♀️", callback_data="gender_female")
    )
    await message.answer("Выберите ваш пол:", reply_markup=keyboard)
    await state.set_state(UserData.waiting_for_gender)

async def gender_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    gender = "мужской" if callback_query.data == "gender_male" else "женский"
    await state.update_data(gender=gender)

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="Низкий  🛌", callback_data="activity_low"),
        InlineKeyboardButton(text="Средний  💪", callback_data="activity_medium"),
        InlineKeyboardButton(text="Высокий  🦾", callback_data="activity_high")
    )
    await callback_query.message.edit_text(
        "Выберите уровень своей физической активности💪\n\n"
        "*Низкий* - означает малоподвижный образ жизни с минимальной физической нагрузкой.\n\n"
        "*Средний* - подразумевает регулярные физические нагрузки, которые могут включать умеренные упражнения, которые не являются слишком интенсивными.\n\n"
        "*Высокий* - это регулярные физические нагрузки высокой интенсивности, проводимые 5-6 раз в неделю, включая кардио и силовые тренировки.",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    await state.set_state(UserData.waiting_for_activity_level)

async def activity_level_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    activity_level_mapping = {
        "activity_low": "1.2",
        "activity_medium": "1.55",
        "activity_high": "1.9"
    }

    activity_level_key = callback_query.data
    activity_level = activity_level_mapping.get(activity_level_key)

    if activity_level is None:
        return

    logging.info(f"Selected activity level: {activity_level}")

    await state.update_data(activity_level=activity_level)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="2", callback_data="meals_2"),
        InlineKeyboardButton(text="3", callback_data="meals_3")
    )
    await callback_query.message.delete()

    # Отправляем новое сообщение с фото и текстом
    await callback_query.message.answer_photo(
        photo="https://i.imgur.com/OsMNHlm.png",
        caption="Теперь расскажите мне, сколько приемов пищи в день будет?🥗",
        reply_markup=keyboard
    )

    # Устанавливаем состояние
    await state.set_state(UserData.waiting_for_meals_per_day)

async def meals_per_day_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext = None):
    meals_per_day = 2 if callback_query.data == "meals_2" else 3
    await state.update_data(meals_per_day=meals_per_day)

    user_data = await state.get_data()

    activity_level_display = {
        "1.2": "Низкий",
        "1.55": "Средний",
        "1.9": "Высокий"
    }

    result_message = get_result_message(user_data, activity_level_display, meals_per_day)

    keyboard = generate_data_confirmation_keyboard()
    await callback_query.message.delete()
    await callback_query.message.answer(result_message, reply_markup=keyboard)
    await state.set_state(UserData.confirming_data)

def register_user_data_handlers(context: AppContext):
    dp = context.dispatcher
    dp.register_message_handler(lambda msg, state=None: height_handler(msg, state, context), state=UserData.waiting_for_height)
    dp.register_message_handler(lambda msg, state=None: weight_handler(msg, state, context), state=UserData.waiting_for_weight)
    dp.register_message_handler(lambda msg, state=None: age_handler(msg, state, context), state=UserData.waiting_for_age)
    dp.register_callback_query_handler(lambda cb, state=None: gender_handler(cb, state, context), state=UserData.waiting_for_gender)
    dp.register_callback_query_handler(lambda cb, state=None: activity_level_handler(cb, state, context), state=UserData.waiting_for_activity_level)
    dp.register_callback_query_handler(lambda cb, state=None: meals_per_day_handler(cb, state, context), state=UserData.waiting_for_meals_per_day)
