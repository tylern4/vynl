from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .migrations import run_migrations
from .routers import albums, auth, recommendations, search, tags, tracks, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.jwt_secret in ("dev-secret-change-me", "change-me", "change-me-in-production"):
        raise RuntimeError(
            "JWT_SECRET is set to a weak default. Set a strong random value in .env before running."
        )
    run_migrations()
    yield


app = FastAPI(title="vynl API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(albums.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
