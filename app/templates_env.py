from fastapi.templating import Jinja2Templates

from app.config import GA_MEASUREMENT_ID, LEGAL_ENTITY_NAME
from app.services.localtime import to_local

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["localtime"] = to_local
templates.env.globals["GA_MEASUREMENT_ID"] = GA_MEASUREMENT_ID
templates.env.globals["LEGAL_ENTITY_NAME"] = LEGAL_ENTITY_NAME
