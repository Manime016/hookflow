
from app.database import engine, Base
import app.models  # noqa: F401 - register all models before create_all

Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
