from handlers.eat_handler.breakfast_handlers import start_breakfast
from handlers.eat_handler.lunch_handlers import start_lunch
from handlers.eat_handler.dinner_handlers import start_dinner

handlers = {
    "breakfast": start_breakfast,
    "lunch": start_lunch,
    "dinner": start_dinner,
}