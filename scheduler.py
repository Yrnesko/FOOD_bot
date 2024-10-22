from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import logging
from handlers.notification_handlers import handlers
from context import AppContext
from aiomysql import DictCursor
from datetime import time, timedelta
import asyncio
from apscheduler.triggers.interval import IntervalTrigger

# Настройка логирования
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# Уменьшение уровня логирования для APScheduler
logging.getLogger('apscheduler').setLevel(logging.WARNING)

scheduler = AsyncIOScheduler()

async def start_scheduler():
    scheduler.start()


async def add_daily_task(context: AppContext, user_id: int, task_time: time, task_type: str, is_scheduled_call=False):
    task_name = f"{task_type}_notification_{user_id}"
    handler = handlers.get(task_type)

    if not handler:
        logging.warning(f"Нет обработчика для типа задачи {task_type}.")
        return

    async with context.pool.acquire() as connection:
        async with connection.cursor(DictCursor) as cursor:
            try:
                # Проверяем, существует ли задача в базе данных
                await cursor.execute(
                    "SELECT * FROM scheduled_tasks WHERE user_id = %s AND task_name = %s AND task_type = %s",
                    (user_id, task_name, task_type)
                )
                existing_task = await cursor.fetchone()

                if existing_task:
                    db_task_time = existing_task['time']

                    # Если время задачи изменилось, обновляем её
                    if db_task_time != task_time:
                        # Проверяем, есть ли задача в планировщике
                        existing_job = scheduler.get_job(task_name)

                        # Удаляем старую задачу из планировщика, если она существует и вызов не по расписанию
                        if existing_job and not is_scheduled_call:
                            try:
                                existing_job.remove()
                                logging.info(f"Удалена старая задача {task_name}.")
                            except Exception as e:
                                logging.error(f"Ошибка при удалении задачи {task_name}: {e}")

                        # Добавляем новую задачу
                        try:
                            scheduler.add_job(
                                handler,
                                CronTrigger(hour=task_time.hour, minute=task_time.minute, timezone=pytz.utc),
                                args=[context.dispatcher, context.pool, user_id],
                                id=task_name,
                                replace_existing=True
                            )
                            logging.info(f"Обновлена задача {task_name}")
                        except Exception as e:
                            logging.error(f"Ошибка при добавлении задачи {task_name}: {e}")

                        # Обновляем задачу в базе данных
                        await cursor.execute(
                            "UPDATE scheduled_tasks SET time = %s WHERE user_id = %s AND task_name = %s AND task_type = %s",
                            (task_time, user_id, task_name, task_type)
                        )
                        await connection.commit()
                else:
                    # Добавляем новую задачу, если её нет в базе данных
                    try:
                        scheduler.add_job(
                            handler,
                            CronTrigger(hour=task_time.hour, minute=task_time.minute, timezone=pytz.utc),
                            args=[context.dispatcher, context.pool, user_id],
                            id=task_name,
                            replace_existing=True
                        )
                        logging.info(f"Добавлена новая задача {task_name}")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении задачи {task_name}: {e}")

                    # Вставляем новую задачу в базу данных
                    await cursor.execute(
                        "INSERT INTO scheduled_tasks (user_id, task_name, time, task_type, is_active) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, task_name, task_time, task_type, True)
                    )
                    await connection.commit()
            except Exception as e:
                logging.error(f"Ошибка при проверке или вставке задачи {task_name} в базу данных: {e}")


async def load_tasks_from_db(context: AppContext):
    async with context.pool.acquire() as connection:
        async with connection.cursor(DictCursor) as cursor:
            try:
                # Загрузка активных задач
                await cursor.execute("SELECT * FROM scheduled_tasks WHERE is_active = TRUE")
                tasks = await cursor.fetchall()
                logging.info(f"Извлечено {len(tasks)} активных задач из базы данных.")

                for task in tasks:
                    try:
                        task_time = task['time']
                        # Преобразуем timedelta в time, если это необходимо
                        if isinstance(task_time, timedelta):
                            delta_seconds = task_time.total_seconds()
                            task_time = time(hour=int(delta_seconds // 3600),
                                             minute=int((delta_seconds % 3600) // 60),
                                             second=int(delta_seconds % 60))

                        await add_daily_task(context, task['user_id'], task_time, task['task_type'])
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении задачи {task}: {e}")

                # Загрузка неактивных задач для удаления
                await cursor.execute("SELECT * FROM scheduled_tasks WHERE is_active = FALSE")
                inactive_tasks = await cursor.fetchall()

                for task in inactive_tasks:
                    try:
                        task_name = f"{task['task_type']}_notification_{task['user_id']}"
                        # Проверяем, существует ли задача в планировщике
                        if existing_job := scheduler.get_job(task_name):
                            existing_job.remove()
                            logging.info(f"Удалена неактивная задача {task_name} из планировщика.")
                        else:
                            logging.info(f"Неактивная задача {task_name} уже удалена.")
                    except Exception as e:
                        logging.error(f"Ошибка при удалении задачи {task_name}: {e}")
            except Exception as e:
                logging.error(f"Ошибка при извлечении задач из базы данных: {e}")


async def reload_scheduled_tasks(context: AppContext):
    try:
        logging.info('Перезагрузка задач запущена')
        await load_tasks_from_db(context)
    except Exception as e:
        logging.error(f"Ошибка при перезагрузке задач: {e}")

async def run_async_task(context):
    await reload_scheduled_tasks(context)

async def schedule_task_reload(context: AppContext, interval_minutes: int= 61 ):
    # Добавляем задачу в планировщик
    scheduler.add_job(
        run_async_task,  # Асинхронная задача
        trigger=IntervalTrigger(minutes=interval_minutes),
        args=[context],
        id='reload_scheduled_tasks',
        replace_existing=True
    )
    logging.info(f"Задача перезагрузки задач запланирована на каждые {interval_minutes} минут.")

async def log_all_jobs():
    """Логирование всех задач в планировщике."""
    jobs = scheduler.get_jobs()
    for job in jobs:
        # Извлечение информации о задаче
        job_info = {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time,
            "trigger": str(job.trigger),  # Преобразуем триггер в строку для удобства
            "func": job.func.__name__,  # Имя функции
            "args": job.args,
            "kwargs": job.kwargs,
            "coalesce": job.coalesce,
            "executor": job.executor,
            "misfire_grace_time": job.misfire_grace_time,
            "max_instances": job.max_instances
        }

        # Логирование информации о задаче
        logging.info(f"Задача: {job_info['id']}, "
                     f"Имя: {job_info['name']}, "
                     f"Следующее выполнение: {job_info['next_run_time']}")
