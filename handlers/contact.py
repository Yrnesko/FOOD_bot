import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
import aiomysql
from states import UserData
from context import AppContext

async def contact_callback_handler(callback_query: types.CallbackQuery, state: FSMContext, context: AppContext):
    tg_user_id = callback_query.from_user.id
    username = callback_query.from_user.first_name
    logging.info(f"Received contact data from user {tg_user_id}. Username: {username}")
    pool = context.pool

    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            try:
                await cursor.execute("SELECT is_registered FROM users WHERE tg_user_id = %s", (tg_user_id,))
                user = await cursor.fetchone()

                if user is None:
                    await cursor.execute("INSERT INTO users (tg_user_id, username, is_registered) VALUES (%s, %s, 0)",
                                       (tg_user_id, username))
                else:
                    await cursor.execute("UPDATE users SET username = %s WHERE tg_user_id = %s", (username, tg_user_id))

                await connection.commit()
            except aiomysql.MySQLError as err:
                logging.error(f"Database error: {err}")

    await state.update_data(tg_user_id=tg_user_id, username=username)
    await callback_query.message.edit_text(f"Здравствуйте, {username}! Какой у вас рост (в см)?")
    await state.set_state(UserData.waiting_for_height)

    logging.info(f"State set to UserData:waiting_for_height for user {tg_user_id}")

def register_contact_handler(context: AppContext):
    dp = context.dispatcher
    dp.register_callback_query_handler(
        lambda cb, state: contact_callback_handler(cb, state, context=context),
        lambda c: c.data == "share_contact"
    )
