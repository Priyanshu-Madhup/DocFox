from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from database import add_chat_message, get_chat_messages

router = APIRouter()

class ChatMessage(BaseModel):
    notebook_id: int
    message: str

class ChatResponse(BaseModel):
    id: int
    message: str
    response: Optional[str]
    created_at: str

@router.post("/")
async def send_message(chat_data: ChatMessage, session_id: str):
    """Send a chat message to a notebook."""
    # Get user from session (simplified session check)
    from routers.auth import active_sessions
    
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user_id = active_sessions[session_id]
    
    # For now, just echo the message as a simple response
    response = f"Echo: {chat_data.message}"
    
    message_id = add_chat_message(
        chat_data.notebook_id, 
        user_id, 
        chat_data.message, 
        response
    )
    
    return {"message_id": message_id, "response": response}

@router.get("/{notebook_id}", response_model=List[ChatResponse])
async def get_notebook_messages(notebook_id: int, session_id: str):
    """Get all chat messages for a notebook."""
    # Get user from session (simplified session check)
    from routers.auth import active_sessions
    
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user_id = active_sessions[session_id]
    messages = get_chat_messages(notebook_id, user_id)
    
    return [ChatResponse(**message) for message in messages]
