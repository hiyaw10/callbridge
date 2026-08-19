from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SECRET_KEY
from app.routers import admin, auth, dashboard, webhooks
from app.templates_env import templates

app = FastAPI(title="CallBridge")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")
