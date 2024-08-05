import fastapi
import db
import logging

user_router = fastapi.APIRouter(prefix="/user", tags=["user"])
logger = logging.getLogger("uvicorn.error")


# @user_router.get("/", tags=["user"])
# def get_users():
#     return db.get_user_ids()
