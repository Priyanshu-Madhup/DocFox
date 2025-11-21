from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from database import create_user, authenticate_user, get_user_by_id

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str

# Simple session storage (in production, use Redis or database)
active_sessions = {}

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserCreate):
    """Register a new user."""
    user_id = create_user(user.username, user.email, user.password)
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    
    return UserResponse(
        id=user_id,
        username=user.username,
        email=user.email
    )

@router.post("/login")
async def login_user(user_credentials: UserLogin):
    """Login user and return user info with session ID."""
    user = authenticate_user(user_credentials.username, user_credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create a simple session (in production, use proper session management)
    session_id = f"session_{user['id']}"
    active_sessions[session_id] = user['id']
    
    return {
        "session_id": session_id,
        "user": user
    }

@router.get("/me")
async def get_current_user_info(session_id: str):
    """Get current user information."""
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user_id = active_sessions[session_id]
    user = get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"user": user}

@router.post("/logout")
async def logout_user(session_id: str):
    """Logout user and invalidate session."""
    if session_id in active_sessions:
        del active_sessions[session_id]
    
    return {"message": "Successfully logged out"}
