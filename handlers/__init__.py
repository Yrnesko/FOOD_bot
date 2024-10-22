
from .start import register_start_handler
from .contact import register_contact_handler
from .user_data import register_user_data_handlers
from handlers.change_data_handler import register_change_data_handlers
from menu.menu_messages import register_menu_messages_handlers
from middlewares.subscription import SubscriptionMiddleware
from handlers.meal_schedule_handler import register_meal_schedule_handlers
from handlers.eat_handler.breakfast_handlers import register_breakfast_handlers
from handlers.eat_handler.lunch_handlers import register_lunch_handlers
from handlers.eat_handler.dinner_handlers import register_dinner_handlers
from context import AppContext
from middlewares.access_control_middleware import register_handlers_with_middleware
from payments import register_payment_handlers
from handlers.eat_handler.snack_handler import register_snack_handlers
from database.function import register_handlers_function


def register_handlers(context: AppContext):
    dp = context.dispatcher
    pool =context.pool
    register_start_handler(context)
    register_contact_handler(context)
    register_user_data_handlers(context)
    register_change_data_handlers(context)
    register_menu_messages_handlers(context)

    dp.middleware.setup(SubscriptionMiddleware(dp, pool))

    register_meal_schedule_handlers(context)
    register_breakfast_handlers(context)
    register_lunch_handlers(context)
    register_dinner_handlers(context)
    register_payment_handlers(context)
    register_snack_handlers(context)

    register_handlers_with_middleware(context)

    register_payment_handlers(context)

    register_handlers_function(context)