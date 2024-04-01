import os
import traceback
from pathlib import Path

import uvicorn as uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi_versioning import VersionedFastAPI
from requests import Request
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from controller.retrain_classifier import retrain_classifier_controller

load_dotenv()

from controller.nomenclature import nomenclature_controller
from controller.file import file_controller
from controller.prediction import prediction_controller
from controller.user import user_controller, auth_controller, tenant_controller, mode_controller, prompt_controller
from controller.chat import message_controller, chat_controller

app = FastAPI()

app.include_router(auth_controller.router, tags=["auth"], prefix="/auth")
app.include_router(user_controller.router, tags=["user"], prefix="/user")
app.include_router(tenant_controller.router, tags=["tenant"], prefix="/tenant")
app.include_router(mode_controller.router, tags=["mode"], prefix="/mode")
# app.include_router(config_controller.router, tags=["config"], prefix="/config")
app.include_router(prompt_controller.router, tags=["prompt"], prefix="/prompt")
app.include_router(chat_controller.router, tags=["chat"], prefix="/chat")
app.include_router(message_controller.router, tags=["message"], prefix="/message")
# app.include_router(mark_controller.router, tags=["mark"], prefix="/mark")
# app.include_router(review_controller.router, tags=["review"], prefix="/review")
app.include_router(prediction_controller.router, tags=["prediction"])
app.include_router(nomenclature_controller.router, tags=["nomenclature"], prefix="/nomenclature")
app.include_router(file_controller.router, tags=["file"], prefix="/file")
app.include_router(retrain_classifier_controller.router, tags=["classifier"], prefix="/retrain_classifier")


# app.include_router(task_controller.router, tags=["task"], prefix="/task")


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"{e}", "traceback": traceback.format_exception(e)},
        )


app = VersionedFastAPI(
    app,
    version_format="{major}",
    prefix_format="/api/v{major}",
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=[os.getenv("FRONTEND_HOST")],
            allow_methods=["POST", "GET", "PUT", "DELETE"],
            allow_headers=["*"],
        )
    ]
)

# app.include_router(task_websocket_controller.router, tags=["task"], prefix="/task/ws")
app.mount("/static/docs", StaticFiles(directory=Path(__file__).parent / ".." / "site", html=True), name="mkdocs")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / ".." / "data"), name="static")


@app.on_event("startup")
def on_startup():
    pass


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
