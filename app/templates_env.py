from fastapi.templating import Jinja2Templates

from app.services.localtime import to_local

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["localtime"] = to_local
