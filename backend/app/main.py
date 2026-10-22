from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.routes.oauth import router as oauth_router
from app.api.v1.routes.auth import router as auth_router
from app.core.config import get_settings
from app.db.session import engine
from app.api.v1.routes.workspace import router as workspace_router
from app.api.v1.routes.csv_upload import router as csv_router
from app.api.v1.routes.analytics import router as analytics_router
# After app = FastAPI(...)
# Alongside your imports:
from app.api.v1.routes.report_editor import router as report_editor_router
from app.api.v1.routes.sharing import private as sharing_router, public as public_sharing_router

# Alongside your existing router registrations, once:


app = FastAPI(title="Trace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Trace-Client"],
    expose_headers=["Retry-After"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    session_cookie="trace_oauth",
    max_age=600,
    same_site="lax",
    https_only=get_settings().cookie_secure,
    path="/api/v1/auth/oauth",
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(report_editor_router, prefix="/api/v1")
app.include_router(sharing_router, prefix="/api/v1")
app.include_router(public_sharing_router, prefix="/api/v1")
app.include_router(csv_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

@app.middleware("http")
async def prevent_auth_caching(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
