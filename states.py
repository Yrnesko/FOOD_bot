from aiogram.dispatcher.filters.state import State, StatesGroup


class UserData(StatesGroup):
    waiting_for_height = State()
    waiting_for_weight = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_activity_level = State()
    waiting_for_meals_per_day = State()
    confirming_data = State()
    showing_menu = State()

    changing_height = State()
    changing_weight = State()
    changing_age = State()
    changing_gender = State()
    changing_activity_level = State()
    changing_meals_per_day = State()
    choosing_parameter_to_change = State()

    managing_subscription = State()
    setting_meal_times = State()
    waiting_for_breakfast_time = State()
    waiting_for_lunch_time = State()
    waiting_for_dinner_time = State()

    confirming_meal_times = State()
    waiting_for_timezone = State()

    changing_meal_times = State()
    waiting_for_change = State()
    editing_options = State()
    changing_breakfast_time = State()
    changing_lunch_time = State()
    changing_dinner_time = State()
    changing_timezone = State()

    waiting_for_meal_time = State()

class BreakfastStates(StatesGroup):
    waiting_for_breakfast = State()
    waiting_for_prep_time = State()
    waiting_for_more_recipes = State()


class LunchStates(StatesGroup):
    waiting_for_lunch = State()
    waiting_for_prep_time = State()
    waiting_for_more_recipes = State()


class DinnerStates(StatesGroup):
    waiting_for_dinner = State()
    waiting_for_prep_time = State()
    waiting_for_more_recipes = State()