from sqlalchemy import Column, Integer, String, Time, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import get_db_config

Base = declarative_base()

class ScheduledTask(Base):
    __tablename__ = 'scheduled_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    task_name = Column(String(50), nullable=False)
    time = Column(Time, nullable=False)
    task_type = Column(String(20), nullable=False)  # Тип задачи (например, завтрак, обед)
    is_active = Column(Boolean, default=True)  # Флаг активности задачи

def get_engine():
    """Создает и возвращает движок SQLAlchemy для подключения к базе данных."""
    db_config = get_db_config()
    # Формат строки подключения для MySQL
    connection_string = (
        f"mysql+pymysql://{db_config['user']}:{db_config['password']}@"
        f"{db_config['host']}/{db_config['database']}"
    )
    return create_engine(connection_string)

def create_tables():
    """Создает таблицы в базе данных на основе определенных моделей."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    create_tables()
