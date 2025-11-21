from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from database import create_notebook, get_user_notebooks, get_user_by_id

router = APIRouter()

class NotebookCreate(BaseModel):
    title: str
    description: Optional[str] = None

class NotebookResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    created_at: str
    updated_at: str

@router.post("/", response_model=int)
async def create_user_notebook(notebook: NotebookCreate, session_id: str):
    """Create a new notebook for the authenticated user."""
    # Get user from session (simplified session check)
    from routers.auth import active_sessions
    
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user_id = active_sessions[session_id]
    notebook_id = create_notebook(user_id, notebook.title, notebook.description)
    
    return notebook_id

@router.get("/", response_model=List[NotebookResponse])
async def get_notebooks(session_id: str):
    """Get all notebooks for the authenticated user."""
    # Get user from session (simplified session check)
    from routers.auth import active_sessions
    
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user_id = active_sessions[session_id]
    notebooks = get_user_notebooks(user_id)
    
    return [NotebookResponse(**notebook) for notebook in notebooks]
