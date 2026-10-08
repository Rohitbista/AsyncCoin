import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from asynccoin.app.routes.auth import router as auth_router
from asynccoin.app.routes.crypto_tracker import router as top_5_router
from asynccoin.config.settings import settings
from asynccoin.database.session import engine
from asynccoin.services.crypto_sync import run_sync_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared HTTP client for the whole app (connection pooling).
    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)

    # Background job: pulls all coins from CoinGecko once now, then every
    # settings.sync_interval_seconds, appending snapshots to the DB.
    # It runs as a task so server startup isn't blocked by the (slow) first pull.
    sync_task = None
    if settings.sync_enabled:
        sync_task = asyncio.create_task(run_sync_scheduler(app.state.http_client), name="crypto-sync")

    yield

    if sync_task:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task
    await app.state.http_client.aclose()
    await engine.dispose()  # close DB connection pool


app = FastAPI(title="Async Coin", lifespan=lifespan)

# Lets a browser frontend on another origin (e.g. localhost:3000) call this API.
# Tighten allow_origins before deploying. (Now also needs POST + Authorization header.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(top_5_router)
app.include_router(auth_router)


@app.get("/")
def root():
    return {"message": "Async Coin is up and running"}


@app.get("/health")
def health():
    return {"status": "ok"}


def main():
    uvicorn.run(
        "asynccoin.app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )