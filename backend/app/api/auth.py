from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas import UserCreate, UserLogin, Token, UserResponse
from backend.app.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    new_user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        role=user_in.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    # Auto-create admin if database is empty
    admin_exists = db.query(User).filter(User.username == "admin").first()
    if not admin_exists and credentials.username == "admin" and credentials.password == "admin123":
        admin_user = User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            role="admin"
        )
        db.add(admin_user)
        db.commit()
        
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

import urllib.parse
from fastapi.responses import RedirectResponse
from backend.app.models import MicrosoftCredential

@router.get("/microsoft/login")
def microsoft_login():
    if settings.MICROSOFT_CLIENT_ID == "mock-client-id-12345":
        # Mock mode redirect directly to callback
        return RedirectResponse(url=f"/api/auth/microsoft/callback?code=mock-auth-code-2026")
    
    # Real Microsoft OAuth redirect URL
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_mode": "query",
        "scope": "https://graph.microsoft.com/Mail.ReadWrite offline_access User.Read",
        "state": "random-state-string-2026"
    }
    url = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)

@router.get("/microsoft/callback")
def microsoft_callback(code: str, db: Session = Depends(get_db)):
    # Exchange token (in mock mode, create fake token, in real mode call OAuth)
    if code == "mock-auth-code-2026":
        email = "mock-operator@swapnanil.onmicrosoft.com"
        access_token = "mock-access-token-12345"
        refresh_token = "mock-refresh-token-12345"
        expires_in = 3600
    else:
        # Real OAuth token exchange
        import requests
        token_url = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
        payload = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET
        }
        res = requests.post(token_url, data=payload)
        if res.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {res.text}")
        data = res.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        # Get user email using MS Graph
        graph_url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_res = requests.get(graph_url, headers=headers)
        if user_res.status_code == 200:
            email = user_res.json().get("mail") or user_res.json().get("userPrincipalName")
        else:
            email = "outlook-connected-user@company.com"

    # Store credentials
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    cred = db.query(MicrosoftCredential).filter(MicrosoftCredential.user_email == email).first()
    if not cred:
        cred = MicrosoftCredential(user_email=email)
        db.add(cred)
    cred.access_token = access_token
    cred.refresh_token = refresh_token
    cred.expires_at = expires_at
    cred.is_active = True
    db.commit()
    
    # Redirect back to react frontend dashboard
    return RedirectResponse(url="http://localhost:5173/?ms_connected=true")

@router.get("/microsoft/status")
def microsoft_status(db: Session = Depends(get_db)):
    cred = db.query(MicrosoftCredential).filter(MicrosoftCredential.is_active == True).first()
    if cred:
        return {
            "connected": True,
            "email": cred.user_email,
            "expires_at": cred.expires_at.isoformat()
        }
    return {"connected": False, "email": None}

@router.post("/microsoft/disconnect")
def microsoft_disconnect(db: Session = Depends(get_db)):
    db.query(MicrosoftCredential).update({MicrosoftCredential.is_active: False})
    db.commit()
    return {"status": "disconnected"}
