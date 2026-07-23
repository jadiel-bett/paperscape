"""PaperScape API routers."""
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.papers import router as papers_router

__all__ = [
    "health_router",
    "jobs_router",
    "papers_router",
]
