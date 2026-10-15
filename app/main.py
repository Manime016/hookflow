
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.endpoint import WebhookEndpoint
from app.schemas.endpoint import EndpointCreate

app = FastAPI(title="HookFlow API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return {"message": "HookFlow API is running"}


@app.post("/endpoints", status_code=status.HTTP_201_CREATED)
def create_endpoint(
    endpoint: EndpointCreate,
    db: Session = Depends(get_db),
):
    db_endpoint = WebhookEndpoint(
        url=str(endpoint.url),
        secret=endpoint.secret,
    )

    try:
        db.add(db_endpoint)
        db.commit()
        db.refresh(db_endpoint)
        return {
            "id": db_endpoint.id,
            "url": db_endpoint.url,
            "is_active": db_endpoint.is_active,
            "created_at": db_endpoint.created_at,
        }
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create endpoint",
        )

@app.get("/endpoints")
def get_endpoints(db: Session = Depends(get_db)):
    endpoints = db.query(WebhookEndpoint).all()
    return endpoints