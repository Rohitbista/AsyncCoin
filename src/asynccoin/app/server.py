from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from asynccoin.app.routes.top_5_crypto_tracker import router as top_5_router
from asynccoin.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared HTTP client for the whole app (connection pooling).
    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="Async Coin", lifespan=lifespan)

# Lets a browser frontend on another origin (e.g. localhost:3000) call this API.
# Tighten allow_origins before deploying.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

app.include_router(top_5_router)


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


if __name__ == "__main__":
    main()