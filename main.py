from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from auth import AuthenticationError
from database import init_db
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(title="Notes App API", lifespan=lifespan)


@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content={"message": exc.message},
        headers={"WWW-Authenticate": "Bearer"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/about")
async def get_about():
    return {
        "name": "Akhand Pratap Shukla",
        "email": "akhandshukla36@gmail.com",
        "my features": {
            "Note Revision History (Audit Trail)": "Instead of overwriting data on PUT requests, the API saves the previous state to a 'revisions' table. I chose this because in robust systems (especially fintech like Fi Money), state mutation without an immutable audit trail is a data vulnerability. This prevents accidental data loss and allows users to track historical changes."
        }
    }


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/app")
async def serve_frontend():
    return FileResponse("static/index.html")

app.include_router(router)
