"""Late-bound application adapters for modular routers; no import-time cycles."""
from fastapi import Depends,Request


def application():
    from . import app
    return app


def db_session():
    yield from application().db_session()


def current_user(request:Request,db=Depends(db_session)):
    return application().current_user(request,db)
