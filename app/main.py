from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routes.endpoints import router as endpoints_router
from app.routes.events import ingestion_router, management_router
from app.middleware import RequestSizeLimitMiddleware
from app.routes.endpoints import get_db

app = FastAPI(
    title="HookFlow API",
    description="Manage destinations that receive webhook events.",
    version="0.1.0",
)


@app.get("/", tags=["health"])
def home() -> dict[str, str]:
    return {"message": "HookFlow API is running"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is unavailable") from error
    return {"status": "ready"}


app.include_router(endpoints_router)
app.include_router(ingestion_router)
app.include_router(management_router)
app.add_middleware(RequestSizeLimitMiddleware)
