"""Authentication and chat history API routes."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr

from api.jwt_utils import create_token, decode_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def get_current_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract user_id from Bearer token. Returns None for guests."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return decode_token(parts[1])


@router.post("/auth/register")
async def register(body: RegisterRequest, request: Request):
    auth_db = request.app.state.auth_db
    try:
        user = auth_db.create_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_token(str(user["id"]))
    return {
        "token": token,
        "user": {"id": str(user["id"]), "email": user["email"]},
    }


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request):
    auth_db = request.app.state.auth_db
    user = auth_db.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user["id"])
    return {"token": token, "user": user}


@router.get("/auth/me")
async def me(request: Request, user_id: Optional[str] = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_db = request.app.state.auth_db
    user = auth_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"user": user}


# --- Chat History Endpoints ---

@router.get("/chat/sessions")
async def list_sessions(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user_id),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required to view sessions")
    auth_db = request.app.state.auth_db
    sessions = auth_db.get_user_sessions(user_id)
    return {"sessions": sessions}


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    user_id: Optional[str] = Depends(get_current_user_id),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    auth_db = request.app.state.auth_db
    messages = auth_db.get_session_messages(session_id)
    return {"messages": messages}
