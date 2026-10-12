from sqlalchemy import text
from app.database import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        print("Connected database:", result.scalar())
        print("MySQL connection successful!")
except Exception as error:
    print("Connection failed:", error)
finally:
    engine.dispose()