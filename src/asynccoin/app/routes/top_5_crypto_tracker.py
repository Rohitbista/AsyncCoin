from fastapi import APIRouter, HTTPException, Request

from asynccoin.app.models import CryptoResponse
from asynccoin.services.fetch_crypto import CryptoFetchError, fetch_top_5_crypto

router = APIRouter()

_CTX = "asynccoin/app/routes/top_5_crypto_tracker"


@router.get("/api/crypto/top5", response_model=CryptoResponse)
async def top_5_crypto(request: Request) -> CryptoResponse:
    try:
        return await fetch_top_5_crypto(request.app.state.http_client)
    except CryptoFetchError as e:
        raise HTTPException(status_code=502, detail=str(e))