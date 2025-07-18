from fastapi import APIRouter

from app.api.routes import agents, items, login, private, users, utils, code_search
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(agents.router)
api_router.include_router(code_search.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
