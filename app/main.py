from fastapi import FastAPI

from app.routes.endpoints import router as endpoints_router

app = FastAPI(
    title="HookFlow API",
    description="Manage destinations that receive webhook events.",
    version="0.1.0",
)


@app.get("/", tags=["health"])
def home() -> dict[str, str]:
    return {"message": "HookFlow API is running"}


app.include_router(endpoints_router)
