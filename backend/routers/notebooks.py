from fastapi import APIRouter, HTTPException, status, Depends
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

@router.post("/", response_model=NotebookResponse)
async def create_notebook(
    notebook: NotebookCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new notebook for the current user."""
    db_notebook = Notebook(
        title=notebook.title,
        user_id=current_user.id
    )
    
    db.add(db_notebook)
    db.commit()
    db.refresh(db_notebook)
    
    return db_notebook

@router.get("/{notebook_id}", response_model=NotebookWithContent)
async def get_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific notebook with its content."""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    return notebook

@router.put("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: int,
    notebook_update: NotebookUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a notebook."""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    if notebook_update.title is not None:
        notebook.title = notebook_update.title
    
    db.commit()
    db.refresh(notebook)
    
    return notebook

@router.delete("/{notebook_id}")
async def delete_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a notebook and all its content."""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    # Delete associated files
    user_dir = get_user_upload_dir(current_user.id)
    notebook_dir = user_dir / f"notebook_{notebook_id}"
    if notebook_dir.exists():
        shutil.rmtree(notebook_dir)
    
    # Delete from database (cascade will handle documents and messages)
    db.delete(notebook)
    db.commit()
    
    return {"message": "Notebook deleted successfully"}

@router.post("/{notebook_id}/documents", response_model=DocumentResponse)
async def upload_document(
    notebook_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a document to a notebook."""
    # Verify notebook ownership
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    # Validate file type
    if not file.content_type == "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported"
        )
    
    # Create user and notebook specific directory
    user_dir = get_user_upload_dir(current_user.id)
    notebook_dir = user_dir / f"notebook_{notebook_id}"
    notebook_dir.mkdir(exist_ok=True)
    
    # Save file
    file_path = notebook_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Extract text from PDF
    extracted_text = extract_pdf_text(str(file_path))
    
    # Create document record
    db_document = Document(
        title=file.filename.replace('.pdf', ''),
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        content_type=file.content_type,
        extracted_text=extracted_text,
        notebook_id=notebook_id
    )
    
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    
    return db_document

@router.delete("/{notebook_id}/documents/{document_id}")
async def delete_document(
    notebook_id: int,
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a document from a notebook."""
    # Verify notebook ownership
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    # Find and delete document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.notebook_id == notebook_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Delete file from filesystem
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    
    # Delete from database
    db.delete(document)
    db.commit()
    
    return {"message": "Document deleted successfully"}

@router.post("/{notebook_id}/process")
async def process_documents(
    notebook_id: int,
    document_ids: List[int],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Process selected documents in a notebook."""
    # Verify notebook ownership
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )
    
    # Get documents to process
    documents = db.query(Document).filter(
        Document.id.in_(document_ids),
        Document.notebook_id == notebook_id
    ).all()
    
    if len(documents) != len(document_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some documents not found"
        )
    
    # Mark documents as processed
    for document in documents:
        document.processed = True
    
    db.commit()
    
    return {
        "message": f"Successfully processed {len(documents)} documents",
        "processed_documents": [doc.id for doc in documents]
    }
