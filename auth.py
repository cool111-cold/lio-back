import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import SessionLocal, ClientsDB, CrmUsersDB

load_dotenv()

SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


def create_access_token(client_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(client_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_crm_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "type": "crm", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_client_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(_get_db),
) -> int:
    payload = _decode_token(credentials.credentials)

    client_id = payload.get("sub")
    if client_id is None or payload.get("type") == "crm":
        raise HTTPException(status_code=401, detail="Invalid token")

    client_id = int(client_id)
    if db.get(ClientsDB, client_id) is None:
        raise HTTPException(status_code=401, detail="Client not found")

    return client_id


def get_optional_client_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(_get_db),
) -> Optional[int]:
    if credentials is None:
        return None
    return get_current_client_id(credentials, db)


def get_current_crm_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(_get_db),
) -> CrmUsersDB:
    payload = _decode_token(credentials.credentials)

    user_id = payload.get("sub")
    if user_id is None or payload.get("type") != "crm":
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(CrmUsersDB, int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="CRM user not found")

    return user


def get_current_crm_admin(user: CrmUsersDB = Depends(get_current_crm_user)) -> CrmUsersDB:
    if user.status != "admin":
        raise HTTPException(status_code=403, detail="Admin rights required")
    return user
