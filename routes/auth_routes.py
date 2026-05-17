from fastapi import APIRouter, HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

from core.auth import criar_token
from core.config import GOOGLE_CLIENT_ID
from core.database import upsert_user

auth_router = APIRouter()


class GoogleTokenRequest(BaseModel):
    id_token: str


@auth_router.post("/auth/google/android")
def auth_google_android(body: GoogleTokenRequest):
    try:
        info = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Token inválido")

    email    = info["email"]
    name     = info.get("name", email)
    username = email.split("@")[0]

    upsert_user(username, name, email)
    return {"token": criar_token(username, email, name), "name": name}