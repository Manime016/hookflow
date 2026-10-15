
from app.database import engine, Base
from app.models.endpoint import WebhookEndpoint

Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
