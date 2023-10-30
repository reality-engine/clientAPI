from fastapi import FastAPI

from . import __version__
from .api import router


def make():
    app = FastAPI(
        version=__version__,
    )
    app.include_router(router, prefix="/connect")
    return app
