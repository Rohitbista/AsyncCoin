from fastapi import APIRouter, Depends, HTTPException, Request

from asynccoin.app.deps import get_current_user
from asynccoin.app.models import CryptoResponse
from asynccoin.services.fetch_crypto import CryptoFetchError, fetch_top_5_crypto

# Router-level dependency: EVERY route on this router requires a valid login,
# including any you add later. (Public routes live on `app` in server.py.)
router = APIRouter(dependencies=[Depends(get_current_user)])

_CTX = "asynccoin/app/routes/top_5_crypto_tracker"

@router.get("/api/crypto/top5", response_model=CryptoResponse)
async def top_5_crypto(request: Request, current_user: dict = Depends(get_current_user)) -> CryptoResponse:
    try:
        # Now you can access the user_id (adjust based on your actual model/dict structure)
        user_id = current_user.id 
        print(f"User {user_id} is requesting crypto data.")

        return await fetch_top_5_crypto(request.app.state.http_client)
    except CryptoFetchError as e:
        raise HTTPException(status_code=502, detail=str(e))