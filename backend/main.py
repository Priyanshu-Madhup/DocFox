from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import re
import requests
from pathlib import Path
from groq import Groq
import PyPDF2
import io
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import uuid
from datetime import datetime
import threading
import http.client
from bs4 import BeautifulSoup
from firecrawl import Firecrawl
from dotenv import load_dotenv
from flashcard_system import FlashcardSystem
from PIL import Image
from io import BytesIO
import edge_tts
import asyncio

# MoviePy imports with error handling
try:
    import moviepy.editor as mp
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    MOVIEPY_AVAILABLE = True
    print("✅ MoviePy loaded successfully")
except ImportError as e:
    print(f"⚠️ MoviePy not available: {e}")
    MOVIEPY_AVAILABLE = False

# Load environment variables
load_dotenv()

# Import simplified reportlab components
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# Import quiz system
from quiz_system import QuizSystem

# Initialize FastAPI app
app = FastAPI(title="DocFox API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Groq client
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
client = Groq(api_key=GROQ_API_KEY)

# Initialize Firecrawl client
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "YOUR_FIRECRAWL_API_KEY_HERE")
firecrawl_client = Firecrawl(api_key=FIRECRAWL_API_KEY)

# Initialize Serper API (for video search)
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "YOUR_SERPER_API_KEY_HERE")

# Initialize SentenceTransformer model for embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# FAISS vector database
vector_dimension = 384  # Dimension for all-MiniLM-L6-v2

def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 characters for English text)"""
    return len(text) // 4

def truncate_chunks_by_tokens(chunks: List[dict], max_tokens: int = 4000) -> List[dict]:
    """Truncate chunks to fit within token limit, preserving most important content"""
    total_tokens = 0
    truncated_chunks = []
    
    for chunk in chunks:
        chunk_text = chunk['chunk']
        chunk_tokens = estimate_tokens(chunk_text)
        
        if total_tokens + chunk_tokens <= max_tokens:
            # Full chunk fits
            truncated_chunks.append(chunk)
            total_tokens += chunk_tokens
        else:
            # Truncate this chunk to fit remaining space
            remaining_tokens = max_tokens - total_tokens
            if remaining_tokens > 100:  # Only add if we have meaningful space left
                # Calculate characters to keep (roughly 4 chars per token)
                chars_to_keep = remaining_tokens * 4
                truncated_text = chunk_text[:chars_to_keep] + "..."
                
                truncated_chunk = chunk.copy()
                truncated_chunk['chunk'] = truncated_text
                truncated_chunks.append(truncated_chunk)
            break
    
    return truncated_chunks
faiss_index = faiss.IndexFlatIP(vector_dimension)  # Inner product for cosine similarity

# Storage for document chunks and metadata
document_store = []
processed_documents = {}

# Initialize quiz system (only needs Groq client, other params passed to methods)
quiz_system = QuizSystem(client)

# Initialize flashcard system
flashcard_system = FlashcardSystem(client)

# Helper functions for RAG system
def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Extract text from PDF bytes"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extracting text from PDF: {str(e)}")

def count_tokens(text: str) -> int:
    """Estimate token count (rough approximation: 1 token ≈ 0.75 words)"""
    words = len(text.split())
    return int(words * 0.75)

def smart_chunk_with_llm(text: str, max_chunk_tokens: int = 400) -> List[str]:
    """Use Groq LLM to determine optimal chunking strategy based on document size"""
    total_tokens = count_tokens(text)
    total_words = len(text.split())
    
    print(f"Document analysis: {total_tokens} tokens, {total_words} words total")
    
    # If document is small enough, return as single chunk
    if total_tokens <= max_chunk_tokens:
        return [text]
    
    try:
        # Ask LLM to determine optimal chunking strategy based on size only
        strategy_prompt = f"""You are analyzing a document with {total_words} words ({total_tokens} tokens total).

Your task: Determine the optimal chunking strategy for a RAG system where each chunk should be around {max_chunk_tokens} tokens.

Based on this document size, provide:
1. Recommended number of chunks
2. Recommended tokens per chunk
3. Should we use sentence boundaries or paragraph boundaries?

Respond with ONLY a JSON object like this:
{{"chunks": 85, "tokens_per_chunk": 300, "boundary_type": "sentence"}}

No explanations, just the JSON."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert document chunking strategist. Provide only JSON responses."},
                {"role": "user", "content": strategy_prompt}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        import json
        strategy = json.loads(response.choices[0].message.content.strip())
        
        # Apply the LLM's strategy using smart overlap chunking
        recommended_chunk_tokens = strategy.get("tokens_per_chunk", max_chunk_tokens)
        boundary_type = strategy.get("boundary_type", "sentence")
        
        print(f"LLM recommends: {strategy['chunks']} chunks of ~{recommended_chunk_tokens} tokens each using {boundary_type} boundaries")
        
        # Use the recommended strategy with smart overlap chunking
        return smart_overlap_chunk(text, recommended_chunk_tokens, boundary_type)
        
    except Exception as e:
        print(f"LLM strategy error: {e}, falling back to smart chunking")
        return smart_overlap_chunk(text, max_chunk_tokens)

def smart_overlap_chunk(text: str, max_chunk_tokens: int = 400, boundary_type: str = "sentence") -> List[str]:
    """Smart chunking with overlap at sentence or paragraph boundaries"""
    chunks = []
    current_chunk = ""
    
    if boundary_type == "paragraph":
        # Split by paragraphs (double newlines)
        splits = text.split('\n\n')
    else:
        # Split by sentences (default)
        splits = text.split('. ')
    
    for split in splits:
        test_chunk = current_chunk + "\n\n" + split if current_chunk and boundary_type == "paragraph" else current_chunk + ". " + split if current_chunk else split
        
        if count_tokens(test_chunk) <= max_chunk_tokens:
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                # Start new chunk with current split
                current_chunk = split
            else:
                # Single split too long, split by words
                words = split.split()
                word_limit = int(max_chunk_tokens / 0.75)
                for i in range(0, len(words), word_limit):
                    chunk_words = words[i:i + word_limit]
                    chunks.append(' '.join(chunk_words))
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into semantically meaningful chunks using LLM analysis"""
    # Convert character-based chunk_size to token-based for smart chunking
    max_tokens = int(chunk_size * 0.3)  # Rough conversion: chars to tokens
    return smart_chunk_with_llm(text, max_tokens)

def add_documents_to_vector_db(chunks: List[str], notebook_id: int, document_name: str):
    """Add document chunks to FAISS vector database"""
    global faiss_index, document_store
    
    # Create embeddings for all chunks
    embeddings = embedding_model.encode(chunks)
    embeddings = embeddings.astype('float32')
    
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)
    
    # Add to FAISS index
    faiss_index.add(embeddings)
    
    # Store metadata
    for i, chunk in enumerate(chunks):
        document_store.append({
            "id": len(document_store),
            "notebook_id": notebook_id,
            "document_name": document_name,
            "chunk": chunk,
            "chunk_index": i
        })

def search_relevant_chunks(query: str, notebook_id: int, top_k: int = 5) -> List[dict]:
    """Search for relevant chunks using FAISS with improved retrieval"""
    print(f"🔍 SEARCH DEBUG: Query='{query}', notebook_id={notebook_id}, top_k={top_k}")
    
    # Increase top_k for comparative/technical questions
    dynamic_top_k = top_k
    if any(term in query.lower() for term in ['compare', 'comparison', 'versus', 'vs', 'difference', 'model', 'protocol']):
        dynamic_top_k = 8  # Return more chunks for comparative questions
        print(f"📝 Increasing result count for comparative question to {dynamic_top_k}")
    
    if faiss_index.ntotal == 0:
        print("🔍 SEARCH DEBUG: FAISS index is empty!")
        return []
    
    print(f"🔍 SEARCH DEBUG: FAISS index has {faiss_index.ntotal} total vectors")
    print(f"🔍 SEARCH DEBUG: Document store has {len(document_store)} documents")
    
    # Check how many docs are for this notebook
    notebook_docs = [doc for doc in document_store if doc["notebook_id"] == notebook_id]
    print(f"🔍 SEARCH DEBUG: Found {len(notebook_docs)} documents for notebook {notebook_id}")
    
    # Create query embedding
    query_embedding = embedding_model.encode([query]).astype('float32')
    faiss.normalize_L2(query_embedding)
    
    # Search in FAISS - get more results initially
    search_k = min(dynamic_top_k * 3, faiss_index.ntotal)  # Get 3x more results for filtering
    scores, indices = faiss_index.search(query_embedding, search_k)
    
    print(f"🔍 SEARCH DEBUG: FAISS returned {len(scores[0])} results with scores: {scores[0][:5]}")
    
    # Filter by notebook_id and return relevant chunks
    relevant_chunks = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(document_store):
            doc = document_store[idx]
            if doc["notebook_id"] == notebook_id:
                # Handle both 'chunk' and 'content' keys for compatibility
                chunk_text = doc.get("chunk") or doc.get("content", "")
                document_name = doc.get("document_name") or doc.get("title", "Unknown Document")
                
                relevant_chunks.append({
                    "chunk": chunk_text,
                    "document_name": document_name,
                    "score": float(score)
                })
                print(f"🔍 SEARCH DEBUG: Added chunk with score {score:.3f} from {document_name}")
    
    print(f"🔍 SEARCH DEBUG: Found {len(relevant_chunks)} relevant chunks after filtering")
    
    # Sort by score (higher is better for cosine similarity)
    relevant_chunks.sort(key=lambda x: x["score"], reverse=True)
    
    # Lower threshold for technical topics that might need keyword fallback
    min_matches = 3
    if any(term in query.lower() for term in ['osi', 'tcp', 'ip', 'model', 'network', 'protocol']):
        min_matches = 4
        print(f"📝 Technical topic detected, requiring more matches: {min_matches}")
    
    # If we don't have enough good matches, try keyword-based fallback
    if len(relevant_chunks) < min_matches:
        print(f"Low similarity matches, trying keyword fallback...")
        keyword_chunks = search_by_keywords(query, notebook_id, dynamic_top_k)
        
        # Combine results
        existing_chunks = {chunk["chunk"][:100] for chunk in relevant_chunks}  # Use first 100 chars as identifier
        for kr in keyword_chunks:
            if kr["chunk"][:100] not in existing_chunks:
                relevant_chunks.append(kr)
                existing_chunks.add(kr["chunk"][:100])
        
        # Sort by score and ensure uniqueness
        seen_chunks = set()
        unique_chunks = []
        for chunk in sorted(relevant_chunks, key=lambda x: x["score"], reverse=True):
            chunk_text = chunk["chunk"][:100]  # Use first 100 chars as identifier
            if chunk_text not in seen_chunks:
                seen_chunks.add(chunk_text)
                unique_chunks.append(chunk)
        relevant_chunks = unique_chunks
    
    return relevant_chunks[:dynamic_top_k]

def search_by_keywords(query: str, notebook_id: int, top_k: int = 3) -> List[dict]:
    """Fallback keyword-based search when semantic search fails"""
    # Basic query words
    query_words = query.lower().split()
    
    # Add domain-specific keywords for common topics
    domain_keywords = []
    
    # For networking/OSI/TCP-IP related queries
    networking_terms = ['osi', 'tcp', 'ip', 'layer', 'protocol', 'network', 'model', 'comparison', 
                       'transport', 'application', 'physical', 'datalink', 'session', 'presentation',
                       'internet', 'host-to-host', 'interface', 'reference']
    
    if any(term in query.lower() for term in ['osi', 'tcp', 'ip', 'model', 'network']):
        domain_keywords.extend(networking_terms)
    
    # Combine all search keywords
    search_terms = set(query_words + domain_keywords)
    print(f"🔍 KEYWORD SEARCH DEBUG: Search terms: {search_terms}")
    
    keyword_chunks = []
    
    for doc in document_store:
        if doc["notebook_id"] == notebook_id:
            chunk_text = doc["chunk"].lower()
            
            # Count direct keyword matches
            direct_matches = sum(1 for word in query_words if word in chunk_text)
            
            # Count domain keyword matches (weighted less than direct matches)
            domain_matches = sum(0.5 for word in domain_keywords if word in chunk_text)
            
            # Check for exact phrases (weighted more)
            phrase_match = 0
            if len(query_words) >= 2:
                query_phrase = ' '.join(query_words)
                if query_phrase.lower() in chunk_text:
                    phrase_match = 3.0  # Give higher weight to exact phrase matches
            
            # Calculate combined score
            total_matches = direct_matches + domain_matches + phrase_match
            
            if total_matches > 0:
                score = total_matches / (len(query_words) + 0.5)  # Normalize score
                
                keyword_chunks.append({
                    "chunk": doc["chunk"],
                    "document_name": doc["document_name"],
                    "score": score  # Combined relevance score
                })
    
    # Sort by keyword matches
    keyword_chunks.sort(key=lambda x: x["score"], reverse=True)
    return keyword_chunks[:top_k]

def save_processed_documents():
    """Save processed documents to JSON file"""
    data = {
        "document_store": document_store,
        "processed_documents": processed_documents,
        "last_updated": datetime.now().isoformat()
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/processed_documents.json", "w") as f:
        json.dump(data, f, indent=2)

def remove_document_from_vector_db(document_name: str, notebook_id: int):
    """Remove all chunks of a specific document from the vector database"""
    global faiss_index, document_store
    
    # Find indices of chunks belonging to this document
    indices_to_remove = []
    remaining_documents = []
    
    for i, doc in enumerate(document_store):
        if doc["document_name"] == document_name and doc["notebook_id"] == notebook_id:
            indices_to_remove.append(i)
        else:
            remaining_documents.append(doc)
    
    if not indices_to_remove:
        return 0  # No chunks found for this document
    
    print(f"Removing {len(indices_to_remove)} chunks for document: {document_name}")
    
    # Rebuild the FAISS index without the removed document
    if len(remaining_documents) > 0:
        # Get all remaining chunks
        remaining_chunks = [doc["chunk"] for doc in remaining_documents]
        
        # Create new embeddings
        embeddings = embedding_model.encode(remaining_chunks)
        embeddings = embeddings.astype('float32')
        faiss.normalize_L2(embeddings)
        
        # Create new FAISS index
        faiss_index = faiss.IndexFlatIP(vector_dimension)
        faiss_index.add(embeddings)
        
        # Update document store with new indices
        for i, doc in enumerate(remaining_documents):
            doc["id"] = i
        
        document_store = remaining_documents
    else:
        # No documents left, reset everything
        faiss_index = faiss.IndexFlatIP(vector_dimension)
        document_store = []
    
    # Remove from processed documents tracking
    if document_name in processed_documents:
        del processed_documents[document_name]
    
    # Save updated state
    save_processed_documents()
    
    return len(indices_to_remove)

# Data storage with file persistence
import json
from pathlib import Path

# Data directory for persistence
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
NOTEBOOKS_FILE = DATA_DIR / "notebooks.json"
UPLOADED_FILES_DIR = DATA_DIR / "uploaded_files"
UPLOADED_FILES_DIR.mkdir(exist_ok=True)

# Load notebooks from file
def load_notebooks():
    global notebooks_storage, next_notebook_id, next_page_id
    try:
        if NOTEBOOKS_FILE.exists():
            with open(NOTEBOOKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                notebooks_storage = data.get('notebooks', [])
                next_notebook_id = data.get('next_notebook_id', 1)
                next_page_id = data.get('next_page_id', 1)
                print(f"Loaded {len(notebooks_storage)} notebooks from file")
        else:
            notebooks_storage = []
            next_notebook_id = 1
            next_page_id = 1
    except Exception as e:
        print(f"Error loading notebooks: {e}")
        notebooks_storage = []
        next_notebook_id = 1
        next_page_id = 1

# Save notebooks to file
def save_notebooks():
    try:
        data = {
            'notebooks': notebooks_storage,
            'next_notebook_id': next_notebook_id,
            'next_page_id': next_page_id
        }
        with open(NOTEBOOKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving notebooks: {e}")

# Initialize storage
notebooks_storage = []
next_notebook_id = 1
next_page_id = 1

# Load existing data on startup
load_notebooks()

def load_processed_documents():
    """Load processed documents from JSON file on startup"""
    global document_store, processed_documents
    try:
        processed_file = Path("data/processed_documents.json")
        if processed_file.exists():
            with open(processed_file, 'r') as f:
                data = json.load(f)
                document_store = data.get("document_store", [])
                processed_documents = data.get("processed_documents", {})
                print(f"Loaded {len(document_store)} document chunks and {len(processed_documents)} processed documents")
                
                # Rebuild FAISS index if we have documents
                if document_store:
                    chunks = [doc["chunk"] for doc in document_store]
                    embeddings = embedding_model.encode(chunks)
                    embeddings = embeddings.astype('float32')
                    faiss.normalize_L2(embeddings)
                    
                    global faiss_index
                    faiss_index = faiss.IndexFlatIP(vector_dimension)
                    faiss_index.add(embeddings)
                    print(f"Rebuilt FAISS index with {len(chunks)} chunks")
        else:
            print("No processed documents file found, starting fresh")
    except Exception as e:
        print(f"Error loading processed documents: {e}")
        document_store = []
        processed_documents = {}

# Load processed documents on startup
load_processed_documents()

# Pydantic models
class NotebookCreate(BaseModel):
    title: str

class NotebookResponse(BaseModel):
    id: int
    title: str
    pages: List[dict] = []
    created_at: str

class PageCreate(BaseModel):
    title: str
    content: Optional[str] = ""

class ChatMessage(BaseModel):
    message: str
    notebook_id: int
    language: str = "en"  # Default to English

class ChatResponse(BaseModel):
    message: str
    response: str

class ProcessPDFRequest(BaseModel):
    notebook_id: int

class ProcessPDFResponse(BaseModel):
    success: bool
    message: str
    document_count: int
    chunks_created: int

class RemoveDocumentRequest(BaseModel):
    document_name: str
    notebook_id: int

class RemoveDocumentResponse(BaseModel):
    success: bool
    message: str
    chunks_removed: int

class WebSearchRequest(BaseModel):
    document_name: str
    notebook_id: int

class WebSearchResponse(BaseModel):
    success: bool
    search_query: str
    chat_response: str
    results_count: int

class ChatPDFRequest(BaseModel):
    notebook_id: int

class WebsiteScrapeRequest(BaseModel):
    url: str

class WebsiteScrapeResponse(BaseModel):
    success: bool
    title: str
    content: str
    url: str
    notebook_id: int
    page_id: int

class VideoSearchRequest(BaseModel):
    document_name: str
    notebook_id: int

class VideoSearchResponse(BaseModel):
    success: bool
    query: str
    videos: List[dict]
    message: str

class VisualPodcastRequest(BaseModel):
    document_name: str
    notebook_id: int

class SlideData(BaseModel):
    title: str
    bullet_points: List[str]
    image_url: str
    audio_url: Optional[str] = None
    slide_number: int

class VisualPodcastResponse(BaseModel):
    success: bool
    slides: List[SlideData]
    total_slides: int
    video_url: Optional[str] = None
    message: str
    message: str

class QuizGenerateRequest(BaseModel):
    notebook_id: int
    num_questions: Optional[int] = 20

class QuizQuestion(BaseModel):
    question_id: int
    question: str
    difficulty: str
    type: str
    expected_key_points: List[str]
    notebook_id: int

class QuizSelectRequest(BaseModel):
    notebook_id: int
    num_questions: int

class QuizAnswerRequest(BaseModel):
    notebook_id: int
    question_id: int
    question: str
    user_answer: str

class QuizEvaluationResponse(BaseModel):
    score: int
    feedback: str
    strengths: List[str]
    weaknesses: List[str]
    suggestions: str
    sources: List[dict]

# Flashcard models
class FlashcardGenerateRequest(BaseModel):
    notebook_id: int
    num_flashcards: Optional[int] = 50

class Flashcard(BaseModel):
    card_id: int
    front: str
    back: str
    category: str

class FlashcardResponse(BaseModel):
    success: bool
    flashcards: List[Flashcard]
    total_flashcards: int
    message: str

# Audio Podcast models
class AudioPodcastRequest(BaseModel):
    document_name: str
    notebook_id: int

class AudioPodcastResponse(BaseModel):
    success: bool
    audio_url: str
    script: str
    duration: Optional[float] = None
    message: str

def clean_text_for_pdf(text):
    """Clean text for PDF rendering to avoid encoding issues"""
    if not text:
        return ""
        
    # Strip HTML tags completely
    text = re.sub(r'</?[a-zA-Z]+[^>]*>', '', text)
    
    # Replace HTML entities
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    
    # Replace problematic characters
    text = text.replace('\u25a0', ' ')  # Replace black boxes
    text = text.replace('\u25a1', ' ')  # Replace white boxes
    text = text.replace('\u2022', '*')  # Replace bullets
    text = text.replace('\u2023', '*')  # Replace triangular bullets
    text = text.replace('\u2043', '*')  # Replace hyphen bullets
    
    # Handle emoji and other special characters (replace with spaces)
    text = ''.join(c if ord(c) < 128 else ' ' for c in text)
    
    return text

def html_to_clean_text(html_content):
    """Convert HTML to properly formatted text using BeautifulSoup"""
    # Handle non-HTML content or already formatted markdown
    if not html_content:
        return ""
        
    if "```html" not in html_content:
        return clean_text_for_pdf(html_content)
    
    # Extract HTML content from code blocks
    parts = html_content.split("```html")
    result = []
    
    # Process each part
    for i, part in enumerate(parts):
        if i == 0:  # Before first HTML block
            result.append(clean_text_for_pdf(part))
            continue
            
        # Handle HTML blocks
        if "```" in part:
            html_part, after_part = part.split("```", 1)
            # Process HTML with BeautifulSoup
            try:
                soup = BeautifulSoup(html_part, "html.parser")
                formatted = format_html_content(soup)
                result.append(clean_text_for_pdf(formatted))
                result.append(clean_text_for_pdf(after_part))
            except Exception as e:
                print(f"Error parsing HTML: {e}")
                result.append(clean_text_for_pdf(part))  # Keep original if parsing fails
        else:
            result.append(clean_text_for_pdf(part))
    
    return "".join(result)

def format_html_content(soup):
    """Format HTML content into clean text"""
    text = ""
    
    # Process HTML elements
    for tag in soup.descendants:
        if tag.name == "h1":
            text += f"\n\n{tag.get_text()}\n{'='*len(tag.get_text())}\n"
        elif tag.name == "h2":
            text += f"\n\n{tag.get_text()}\n{'-'*len(tag.get_text())}\n"
        elif tag.name == "h3":
            text += f"\n\n{tag.get_text()}\n"
        elif tag.name == "p":
            text += f"\n{tag.get_text()}\n"
        elif tag.name == "blockquote":
            lines = tag.get_text().split('\n')
            text += "\n" + "\n".join([f"> {line}" for line in lines]) + "\n"
        elif tag.name == "table":
            text += "\n\n"
            # Process table rows
            for row in tag.find_all("tr"):
                cells = []
                for cell in row.find_all(["th", "td"]):
                    cells.append(cell.get_text().strip())
                text += " | ".join(cells) + "\n"
            text += "\n"
        elif tag.name == "hr":
            text += "\n" + "-"*50 + "\n"
        elif tag.name == "ul" or tag.name == "ol":
            for i, li in enumerate(tag.find_all("li", recursive=False)):
                prefix = "• " if tag.name == "ul" else f"{i+1}. "
                text += f"\n{prefix}{li.get_text()}"
            text += "\n"
        elif tag.name == "code" or tag.name == "pre":
            text += f"\n```\n{tag.get_text()}\n```\n"
    
    return text

def format_chat_for_pdf(chat_history):
    """Format the chat history into a clean text format for PDF"""
    formatted_text = ""
    
    # Create special formatted content for PDF
    try:
        # Process each message
        for msg in chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Additional cleaning for black boxes and other Unicode
            if "■" in content:
                content = content.replace("■", " ")
            if "□" in content:
                content = content.replace("□", " ")
                
            # Replace any unusual space characters
            content = content.replace("\u00A0", " ")  # Non-breaking space
            content = content.replace("\u2003", " ")  # Em space
            content = content.replace("\u2002", " ")  # En space
            
            # Strip HTML tags directly
            content = re.sub(r'</?(?:p|strong|li|ul|code|pre|h1|h2|h3|h4|h5|blockquote)[^>]*>', '', content)
            content = re.sub(r'</(?:p|strong|li|ul|code|pre|h1|h2|h3|h4|h5|blockquote)>', '\n', content)
            
            # Clean HTML content if present
            clean_content = html_to_clean_text(content)
            
            # Final strip of any remaining HTML tags
            clean_content = re.sub(r'</?[^>]+>', '', clean_content)
            
            # Add formatted message to output
            if role == "user":
                formatted_text += "\n\nUser Message:\n"
                formatted_text += "-" * 50 + "\n"
                formatted_text += clean_content + "\n"
            else:
                formatted_text += "\n\nDocFox Response:\n"
                formatted_text += "-" * 50 + "\n"
                formatted_text += clean_content + "\n"
    except Exception as e:
        print(f"Error in format_chat_for_pdf: {e}")
        formatted_text += f"\nError processing chat: {str(e)}\n"
    
    return formatted_text

# Routes
@app.get("/")
async def root():
    return {"message": "DocFox API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "groq_available": True}

@app.post("/notebooks", response_model=NotebookResponse)
async def create_notebook(notebook: NotebookCreate):
    global next_notebook_id
    
    new_notebook = {
        "id": next_notebook_id,
        "title": notebook.title,
        "pages": [],
        "chat_history": [],  # Store chat messages per notebook
        "created_at": datetime.now().isoformat()
    }
    
    notebooks_storage.append(new_notebook)
    next_notebook_id += 1
    save_notebooks()  # Save after modification
    
    return new_notebook

@app.get("/notebooks", response_model=List[NotebookResponse])
async def get_notebooks():
    # Sort notebooks by creation/update time (most recent first)
    sorted_notebooks = sorted(notebooks_storage, key=lambda x: x.get("updated_at", x.get("created_at", "1970-01-01T00:00:00Z")), reverse=True)
    return sorted_notebooks

@app.get("/notebooks/{notebook_id}")
async def get_notebook(notebook_id: int):
    notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id), None)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook

@app.get("/notebooks/{notebook_id}/processed-documents")
async def get_processed_documents(notebook_id: int):
    """Get list of processed documents for a specific notebook"""
    
    # Find documents processed for this notebook
    processed_docs = []
    for doc_name, doc_info in processed_documents.items():
        if doc_info.get("notebook_id") == notebook_id:
            processed_docs.append({
                "filename": doc_name,
                "chunks_count": doc_info.get("chunks_count", 0),
                "processed_at": doc_info.get("processed_at")
            })
    
    return {
        "notebook_id": notebook_id,
        "processed_documents": processed_docs,
        "total_processed": len(processed_docs)
    }

@app.put("/notebooks/{notebook_id}")
async def update_notebook(notebook_id: int, notebook_update: dict):
    """Update notebook title and other properties"""
    
    print(f"Updating notebook {notebook_id} with data: {notebook_update}")
    
    notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id), None)
    if not notebook:
        print(f"Notebook {notebook_id} not found")
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    # Update allowed fields
    if "title" in notebook_update:
        old_title = notebook["title"]
        notebook["title"] = notebook_update["title"]
        notebook["updated_at"] = datetime.now().isoformat()
        print(f"Updated notebook title from '{old_title}' to '{notebook['title']}'")
    
    # Save changes to file
    save_notebooks()
    print(f"Saved notebooks to file")
    
    return notebook

@app.post("/notebooks/{notebook_id}/pages")
async def add_page_to_notebook(notebook_id: int, page: PageCreate):
    global next_page_id
    
    notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id), None)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    new_page = {
        "id": next_page_id,
        "title": page.title,
        "content": page.content,
        "type": "text"
    }
    
    notebook["pages"].append(new_page)
    next_page_id += 1
    
    return new_page

@app.post("/process-pdf", response_model=ProcessPDFResponse)
async def process_pdf_documents(
    notebook_id: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    persisted_files: str = Form(default="[]")
):
    """Process PDF files and add to vector database"""
    
    try:
        # Convert notebook_id from string to int
        notebook_id_int = int(notebook_id)
        
        # Parse persisted files
        persisted_file_list = []
        try:
            if persisted_files and persisted_files != "[]":
                persisted_file_list = json.loads(persisted_files)
        except json.JSONDecodeError:
            persisted_file_list = []
        
        total_files = len(files) + len(persisted_file_list)
        print(f"Processing {len(files)} new files + {len(persisted_file_list)} persisted files for notebook {notebook_id_int}")
        
        # Ensure notebook exists
        notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id_int), None)
        if not notebook:
            # Auto-create notebook if it doesn't exist
            global next_notebook_id
            new_notebook = {
                "id": notebook_id_int,
                "title": f"Notebook {notebook_id_int}",
                "pages": [],
                "chat_history": [],
                "created_at": datetime.now().isoformat()
            }
            notebooks_storage.append(new_notebook)
            next_notebook_id = max(next_notebook_id, notebook_id_int + 1)
            notebook = new_notebook
            print(f"Auto-created notebook: {new_notebook}")
        
        total_chunks = 0
        processed_files = 0
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                continue
                
            print(f"Processing file: {file.filename}")
            
            # Save uploaded file to disk
            file_path = UPLOADED_FILES_DIR / f"{notebook_id_int}_{file.filename}"
            with open(file_path, "wb") as f:
                pdf_content = await file.read()
                f.write(pdf_content)
            
            # Reset file position for text extraction
            # Extract text
            text = extract_text_from_pdf(pdf_content)
            
            if not text.strip():
                print(f"No text extracted from {file.filename}")
                continue
            
            # Analyze document
            total_tokens = count_tokens(text)
            word_count = len(text.split())
            
            print(f"Document analysis for {file.filename}:")
            print(f"  - Total words: {word_count}")
            print(f"  - Estimated tokens: {total_tokens}")
            print(f"  - Character count: {len(text)}")
            
            # Create intelligent chunks using LLM
            chunks = chunk_text(text)
            
            print(f"  - Created {len(chunks)} semantic chunks")
            for i, chunk in enumerate(chunks):
                chunk_tokens = count_tokens(chunk)
                print(f"    Chunk {i+1}: {chunk_tokens} tokens, {len(chunk.split())} words")
            
            # Add to vector database
            add_documents_to_vector_db(chunks, notebook_id_int, file.filename)
            
            # Update notebook with document reference
            new_page = {
                "id": len(notebook["pages"]) + 1,
                "title": f"📄 {file.filename}",
                "content": f"PDF document: {word_count} words, {total_tokens} tokens, {len(chunks)} semantic chunks",
                "type": "pdf",
                "filename": file.filename,
                "file_path": str(file_path),  # Store file path for persistence
                "chunks_count": len(chunks),
                "word_count": word_count,
                "token_count": total_tokens
            }
            notebook["pages"].append(new_page)
            
            # Track processed document
            processed_documents[file.filename] = {
                "notebook_id": notebook_id_int,
                "chunks_count": len(chunks),
                "processed_at": datetime.now().isoformat()
            }
            
            total_chunks += len(chunks)
            processed_files += 1
        
        # Process persisted files
        for persisted_file in persisted_file_list:
            filename = persisted_file.get('filename')
            if not filename:
                continue
                
            print(f"Processing persisted file: {filename}")
            
            # Check if file exists on disk
            file_path = UPLOADED_FILES_DIR / f"{notebook_id_int}_{filename}"
            if not file_path.exists():
                print(f"Persisted file not found: {file_path}")
                continue
            
            # Read existing file
            with open(file_path, "rb") as f:
                pdf_content = f.read()
            
            # Extract text
            text = extract_text_from_pdf(pdf_content)
            
            if not text.strip():
                print(f"No text extracted from persisted file {filename}")
                continue
            
            # Check if already in vector DB
            if filename in processed_documents and processed_documents[filename].get("notebook_id") == notebook_id_int:
                print(f"File {filename} already processed for this notebook")
                continue
            
            # Analyze document
            total_tokens = count_tokens(text)
            word_count = len(text.split())
            
            # Create intelligent chunks using LLM
            chunks = chunk_text(text)
            
            # Add to vector database
            add_documents_to_vector_db(chunks, notebook_id_int, filename)
            
            # Track processed document
            processed_documents[filename] = {
                "notebook_id": notebook_id_int,
                "chunks_count": len(chunks),
                "processed_at": datetime.now().isoformat()
            }
            
            total_chunks += len(chunks)
            processed_files += 1
        
        # Save to JSON
        save_processed_documents()
        save_notebooks()  # Save notebook state with new pages
        
        print(f"Successfully processed {processed_files} files with {total_chunks} chunks")
        
        return ProcessPDFResponse(
            success=True,
            message=f"Successfully processed {processed_files} PDF files",
            document_count=processed_files,
            chunks_created=total_chunks
        )
        
    except Exception as e:
        print(f"Error processing PDFs: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing PDFs: {str(e)}")

@app.post("/remove-document", response_model=RemoveDocumentResponse)
async def remove_document_from_processing(request: RemoveDocumentRequest):
    """Remove a specific document from the vector database"""
    
    try:
        print(f"Removing document: {request.document_name} from notebook {request.notebook_id}")
        
        # Remove from vector database
        chunks_removed = remove_document_from_vector_db(request.document_name, request.notebook_id)
        
        # Remove from notebook pages
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if notebook:
            notebook["pages"] = [
                page for page in notebook["pages"] 
                if not (page.get("filename") == request.document_name and page.get("type") == "pdf")
            ]
            save_notebooks()  # Save after removing pages
        
        print(f"Successfully removed {chunks_removed} chunks for document: {request.document_name}")
        
        return RemoveDocumentResponse(
            success=True,
            message=f"Successfully removed document: {request.document_name}",
            chunks_removed=chunks_removed
        )
        
    except Exception as e:
        print(f"Error removing document: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error removing document: {str(e)}")

@app.get("/notebooks/{notebook_id}/summary")
async def get_notebook_summary(notebook_id: int, document_name: str = None):
    """Get a comprehensive summary of documents in a notebook for mindmap generation
    
    Args:
        notebook_id: The notebook ID
        document_name: Optional specific document name. If provided, only that document is summarized.
    """
    
    try:
        if document_name:
            print(f"Generating summary for document '{document_name}' in notebook {notebook_id}")
        else:
            print(f"Generating summary for notebook {notebook_id}")
        
        # Get chunks for this notebook, optionally filtered by document
        if document_name:
            notebook_chunks = [doc for doc in document_store 
                             if doc["notebook_id"] == notebook_id and doc["document_name"] == document_name]
            print(f"Found {len(notebook_chunks)} chunks for document '{document_name}' in notebook {notebook_id}")
        else:
            notebook_chunks = [doc for doc in document_store if doc["notebook_id"] == notebook_id]
            print(f"Found {len(notebook_chunks)} chunks for notebook {notebook_id}")
        
        if not notebook_chunks:
            if document_name:
                return {
                    "summary": f"No content found for document '{document_name}'. Please make sure the document is uploaded and processed.",
                    "document_name": document_name,
                    "document_count": 0,
                    "total_chunks": 0
                }
            else:
                return {
                    "summary": "No documents found in this notebook. Please upload some documents first to generate a mindmap.",
                    "document_count": 0,
                    "total_chunks": 0
                }
        
        # Group chunks by document
        documents = {}
        for chunk in notebook_chunks:
            doc_name = chunk["document_name"]
            if doc_name not in documents:
                documents[doc_name] = []
            documents[doc_name].append(chunk["chunk"])
        
        # Create a comprehensive summary prompt
        all_content = ""
        for doc_name, chunks in documents.items():
            all_content += f"\n\n=== {doc_name} ===\n"
            all_content += "\n".join(chunks[:10])  # Limit chunks per document
        
        # Determine if this is a single document or multiple documents
        is_single_document = len(documents) == 1
        doc_description = f"document '{document_name}'" if document_name else f"{len(documents)} documents"
        
        # Generate hierarchical summary using Groq
        summary_prompt = f"""Analyze the following {doc_description} and create a detailed hierarchical summary suitable for a mindmap visualization.

Structure your response as:
1. Main Topic/Theme
   - Subtopic 1
     • Key point
     • Key point
   - Subtopic 2
     • Key point
     • Key point
2. Second Main Topic
   ...and so on

Focus on:
- Main themes and concepts
- Important subtopics and categories  
- Key facts, findings, or points
- Relationships between ideas
- Clear hierarchical structure

{"Document" if is_single_document else "Documents"} content:
{all_content[:8000]}"""  # Limit content to avoid token limits

        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert at creating structured summaries for knowledge visualization. Create clear hierarchical summaries perfect for mindmap trees."
                },
                {
                    "role": "user",
                    "content": summary_prompt
                }
            ],
            temperature=0.3,
            max_tokens=1500
        )
        
        summary = completion.choices[0].message.content
        
        result = {
            "summary": summary,
            "document_count": len(documents),
            "total_chunks": len(notebook_chunks)
        }
        
        # Add document name if this was a single document request
        if document_name:
            result["document_name"] = document_name
            
        return result
        
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return {"error": f"Failed to generate summary: {str(e)}"}

@app.get("/notebooks/{notebook_id}/chat")
async def get_chat_history(notebook_id: int):
    """Get chat history for a specific notebook"""
    notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id), None)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    return {"chat_history": notebook.get("chat_history", [])}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_groq(chat_message: ChatMessage):
    """Chat endpoint using Groq's latest GPT OSS model"""
    
    try:
        print(f"Received chat request: {chat_message}")
        print(f"Available notebooks: {notebooks_storage}")
        
        # Auto-create default notebook if none exists and user is asking for notebook ID 1
        if not notebooks_storage and chat_message.notebook_id == 1:
            global next_notebook_id
            default_notebook = {
                "id": 1,
                "title": "My First Notebook",
                "pages": [],
                "chat_history": [],
                "created_at": "2025-08-10T00:00:00Z"
            }
            notebooks_storage.append(default_notebook)
            next_notebook_id = 2
            print(f"Auto-created default notebook: {default_notebook}")
        
        # Get notebook context
        notebook = next((nb for nb in notebooks_storage if nb["id"] == chat_message.notebook_id), None)
        if not notebook:
            print(f"Notebook with ID {chat_message.notebook_id} not found")
            raise HTTPException(status_code=404, detail="Notebook not found")
        
        print(f"Found notebook: {notebook}")
        
        # Ensure notebook has chat_history (for backwards compatibility)
        if "chat_history" not in notebook:
            notebook["chat_history"] = []
        
        # Prepare context from notebook pages and RAG
        context = f"Notebook: {notebook['title']}\n"
        
        # Add document pages info
        if notebook['pages']:
            context += "Available documents:\n"
            for page in notebook['pages']:
                if page.get('type') == 'pdf':
                    context += f"- {page['title']}: PDF with {page.get('chunks_count', 0)} chunks\n"
                else:
                    context += f"- {page['title']}: {page.get('content', 'No content available')}\n"
        else:
            context += "No documents uploaded yet.\n"
        
        # Search for relevant chunks using RAG
        print(f"Searching for chunks with query: '{chat_message.message}' for notebook: {chat_message.notebook_id}")
        print(f"Total documents in store: {len(document_store)}")
        print(f"FAISS index size: {faiss_index.ntotal}")
        
        relevant_chunks = search_relevant_chunks(chat_message.message, chat_message.notebook_id)
        print(f"Found {len(relevant_chunks)} relevant chunks")
        
        if relevant_chunks:
            for i, chunk in enumerate(relevant_chunks):
                print(f"Chunk {i+1} score: {chunk['score']}, from: {chunk['document_name']}")
                print(f"Chunk preview: {chunk['chunk'][:200]}...")
        else:
            print("No relevant chunks found!")
            # Debug: check what's in document store for this notebook
            notebook_docs = [doc for doc in document_store if doc["notebook_id"] == chat_message.notebook_id]
            print(f"Documents for notebook {chat_message.notebook_id}: {len(notebook_docs)}")
            if notebook_docs:
                print(f"Sample document: {notebook_docs[0]['document_name']}")
                print(f"Sample chunk preview: {notebook_docs[0]['chunk'][:200]}...")
                # Try a simple keyword search to see if content exists
                query_lower = chat_message.message.lower()
                matching_docs = []
                for doc in notebook_docs:
                    if any(word in doc['chunk'].lower() for word in ['osi', 'tcp', 'ip', 'network', 'layer', 'protocol']):
                        matching_docs.append(doc)
                print(f"Found {len(matching_docs)} docs with networking keywords")
                if matching_docs:
                    print(f"Sample matching chunk: {matching_docs[0]['chunk'][:300]}...")
        
        rag_context = ""
        if relevant_chunks:
            # Truncate chunks to prevent token limit issues
            truncated_chunks = truncate_chunks_by_tokens(relevant_chunks, max_tokens=4000)
            print(f"Truncated from {len(relevant_chunks)} to {len(truncated_chunks)} chunks for token limits")
            
            rag_context = "\n\nRelevant document excerpts:\n"
            for i, chunk_data in enumerate(truncated_chunks):
                chunk_tokens = estimate_tokens(chunk_data['chunk'])
                print(f"Chunk {i+1}: {chunk_tokens} estimated tokens from {chunk_data['document_name']}")
                rag_context += f"\n[From {chunk_data['document_name']}]:\n{chunk_data['chunk']}\n"
        
        full_context = context + rag_context
        
        # Check total token count before API call
        total_estimated_tokens = estimate_tokens(full_context) + estimate_tokens(chat_message.message) + 1000  # Extra buffer for system message
        print(f"Estimated total tokens for API call: {total_estimated_tokens}")
        
        if total_estimated_tokens > 7000:  # Keep well under 8000 limit
            print(f"⚠️ Token count too high ({total_estimated_tokens}), further reducing context...")
            # Further reduce chunks if still too large
            if relevant_chunks:
                reduced_chunks = truncate_chunks_by_tokens(relevant_chunks, max_tokens=2000)
                rag_context = "\n\nRelevant document excerpts:\n"
                for chunk_data in reduced_chunks:
                    rag_context += f"\n[From {chunk_data['document_name']}]:\n{chunk_data['chunk']}\n"
                full_context = context + rag_context
                print(f"Reduced to {estimate_tokens(full_context)} tokens")
        
        print(f"Calling Groq API with message: {chat_message.message}")
        
        # Language mapping for response instructions
        language_names = {
            "en": "English",
            "es": "Spanish", 
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi"
        }
        
        response_language = language_names.get(chat_message.language, "English")
        
        # First API call - Get the content response with RAG context
        system_message = f"""You are a helpful AI assistant called DocFox. You have access to document content through a retrieval system.

IMPORTANT: Respond in {response_language} language.

When answering questions:
1. Use the provided document excerpts when relevant
2. Cite the document names when referencing specific information
3. If the question can't be answered from the provided context, say so clearly
4. Provide comprehensive answers based on the available information
5. For technical comparison questions (like comparing OSI vs TCP/IP models), provide:
   - A clear explanation of both concepts/models individually
   - A structured comparison with key differences highlighted in a table format if applicable
   - A detailed analysis of the similarities and differences between the concepts
   - Visual structure using bullet points, numbered lists, or tables for clarity
   - A conclusion about practical applications or industry preferences
6. IMPORTANT: Always provide COMPLETE answers - never cut off mid-explanation
7. Use bullet points and structure for clarity

Context: {full_context}"""

        # Check if the query is related to networking models or other technical comparisons
        if any(term in chat_message.message.lower() for term in ['osi', 'tcp/ip', 'tcp-ip', 'compare', 'difference between']):
            system_message += f"""

For this specific technical comparison (respond in {response_language}):
- Ensure you cover ALL layers of both models completely
- Explain the PURPOSE of each layer
- Explain which PROTOCOLS operate at each layer
- Include a clear table showing the mapping between different models
- Make sure your response is complete and not truncated"""

        first_completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": chat_message.message
                }
            ],
            max_tokens=2048  # Ensure we get complete responses
        )
        
        raw_response = first_completion.choices[0].message.content
        print(f"First API call response: {raw_response}")
        
        # Second API call - Format the response as HTML
        second_completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are an HTML formatter. Your job is to take plain text content and format it as clean HTML for better readability.

IMPORTANT: Maintain the content in {response_language} language. Do not translate or change the language of the content.

FORMATTING RULES:
- Wrap paragraphs in <p> tags
- Use <h1>, <h2>, <h3> for any headings you identify
- Use <ul> and <li> for bullet points or lists
- Use <ol> and <li> for numbered lists
- Use <strong> for important/bold text
- Use <em> for emphasized text
- Use <code> for any code snippets
- Use <pre><code> for code blocks
- Use <table>, <tr>, <th>, <td> for tabular data
- Keep the original meaning and content exactly the same
- Return ONLY the HTML content, no markdown code blocks, no ```html wrapper, no explanations
- Start directly with HTML tags like <h1> or <p>, not with ```html"""
                },
                {
                    "role": "user",
                    "content": f"Please format this text as HTML:\n\n{raw_response}"
                }
            ]
        )
        
        response_text = second_completion.choices[0].message.content
        print(f"HTML formatted response: {response_text}")
        
        # Clean up markdown code blocks if present
        if response_text.startswith('```html'):
            response_text = response_text[7:]  # Remove ```html
        if response_text.endswith('```'):
            response_text = response_text[:-3]  # Remove closing ```
        response_text = response_text.strip()  # Remove any extra whitespace
        if response_text.startswith('```html'):
            response_text = response_text.replace('```html', '').replace('```', '').strip()
        elif response_text.startswith('```'):
            response_text = response_text.replace('```', '', 1).replace('```', '').strip()
        
        print(f"Cleaned HTML response: {response_text[:200]}...")
        
        # Store the conversation in notebook's chat history
        notebook["chat_history"].append({
            "id": f"{len(notebook['chat_history']) + 1}-u",
            "role": "user",
            "content": chat_message.message,
            "timestamp": datetime.now().isoformat()
        })
        notebook["chat_history"].append({
            "id": f"{len(notebook['chat_history']) + 1}-a", 
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat()
        })
        
        return ChatResponse(
            message=chat_message.message,
            response=response_text
        )
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error communicating with Groq: {str(e)}")

@app.post("/web-search", response_model=WebSearchResponse)
async def web_search(request: WebSearchRequest):
    """Generate a web search query based on document summary and fetch results"""
    try:
        print(f"Starting web search for document: {request.document_name}, notebook: {request.notebook_id}")
        
        # Step 1: Get document chunks directly from document_store (no similarity search needed)
        if not document_store:
            raise HTTPException(status_code=404, detail="No documents found. Please upload and process a PDF first.")
        
        # Get ALL chunks for the specific document
        document_chunks = [
            doc for doc in document_store 
            if doc["notebook_id"] == request.notebook_id and doc["document_name"] == request.document_name
        ]
        
        if not document_chunks:
            # If no chunks found, let's see what documents are available
            available_docs = set()
            for doc in document_store:
                if doc["notebook_id"] == request.notebook_id:
                    available_docs.add(doc["document_name"])
            print(f"Available documents for notebook {request.notebook_id}: {available_docs}")
            raise HTTPException(status_code=404, detail=f"Document '{request.document_name}' not found. Available documents: {list(available_docs)}")
        
        print(f"Found {len(document_chunks)} chunks for document '{request.document_name}'")
        
        # Create summary from first 5 chunks to get good document overview
        summary_text = ""
        for chunk in document_chunks[:5]:
            chunk_text = chunk.get("chunk") or chunk.get("content", "")
            summary_text += chunk_text + "\n\n"
        
        # Limit summary length
        if len(summary_text) > 2000:
            summary_text = summary_text[:2000] + "..."
        
        print(f"Got document summary: {len(summary_text)} characters from {min(5, len(document_chunks))} chunks")
        
        # Step 2: Ask Groq for search query
        search_query_prompt = f"""Based on this document content, create a focused web search query to find recent news, updates, or related information:

{summary_text}

Respond with only a short search query (2-6 words):"""
        
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": search_query_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=30
        )
        
        search_query = completion.choices[0].message.content.strip().strip('"').strip("'")
        print(f"Generated search query: '{search_query}'")
        
        # Step 3: Use Serper API
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({"q": search_query, "num": 8})
        headers = {
            'X-API-KEY': '67c090a334109db4480037614dbb1c635f29ad83',
            'Content-Type': 'application/json'
        }
        
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        data = res.read()
        search_results = json.loads(data.decode("utf-8"))
        
        print(f"Serper API returned status: {res.status}")
        
        # Step 4: Process search results with Groq
        if search_results.get("organic"):
            # Format the search results for Groq
            results_text = f"Search Query: '{search_query}'\n\nWeb Search Results:\n\n"
            for i, result in enumerate(search_results["organic"][:6], 1):
                results_text += f"{i}. **{result.get('title', 'No title')}**\n"
                results_text += f"   Source: {result.get('link', 'No link')}\n"
                results_text += f"   Summary: {result.get('snippet', 'No description')}\n\n"
            
            # Ask Groq to analyze and summarize the web search results
            analysis_prompt = f"""Based on the document content and these web search results, provide a comprehensive analysis:

DOCUMENT SUMMARY:
{summary_text[:800]}

WEB SEARCH RESULTS:
{results_text}

Please provide:
1. A summary of what the web search found related to the document
2. Key insights and recent developments 
3. How the web results connect to or expand on the document content
4. Any important updates or news related to the topic

Format your response in a clear, organized way with proper headings."""

            analysis_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": analysis_prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=800
            )
            
            raw_analysis = analysis_completion.choices[0].message.content
            
            # Format the response as HTML (same as regular chat)
            html_format_completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an HTML formatter. Your job is to take plain text content and format it as clean HTML for better readability.

FORMATTING RULES:
- Wrap paragraphs in <p> tags
- Use <h1>, <h2>, <h3> for any headings you identify
- Use <ul> and <li> for bullet points or lists
- Use <ol> and <li> for numbered lists
- Use <strong> for important/bold text
- Use <em> for emphasized text
- Use <code> for any code snippets
- Use <pre><code> for code blocks
- Use <table>, <tr>, <th>, <td> for tabular data
- Keep the original meaning and content exactly the same
- Only return the HTML formatted version, no explanations"""
                    },
                    {
                        "role": "user",
                        "content": f"Please format this text as HTML:\n\n{raw_analysis}"
                    }
                ]
            )
            
            chat_response = html_format_completion.choices[0].message.content
            results_count = len(search_results["organic"])
        else:
            chat_response = f"I searched for '{search_query}' but didn't find relevant web results. The search may need to be refined or the topic might not have recent online coverage."
            results_count = 0
        
        # Step 5: Add web search results directly to chat history
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if notebook:
            # Add user message for the web search action
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-u",
                "role": "user", 
                "content": f"🌐 Web Search: {request.document_name}",
                "timestamp": datetime.now().isoformat()
            })
            
            # Add bot response with the analysis
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-a", 
                "role": "assistant",
                "content": f"<h2>🌐 Web Search Results for {request.document_name}</h2><p><strong>Search Query:</strong> {search_query}</p>{chat_response}",
                "timestamp": datetime.now().isoformat()
            })
        
        return WebSearchResponse(
            success=True,
            search_query=search_query,
            chat_response=chat_response,
            results_count=results_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Web search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")


    
    return formatted_videos

@app.post("/video-search", response_model=VideoSearchResponse)
async def video_search(request: VideoSearchRequest):
    """Generate YouTube video search based on document summary and fetch results"""
    try:
        print(f"Starting video search for document: {request.document_name}, notebook: {request.notebook_id}")
        
        # Step 1: Get document chunks directly from document_store (no similarity search needed)
        if not document_store:
            raise HTTPException(status_code=404, detail="No documents found. Please upload and process a PDF first.")
        
        # Get ALL chunks for the specific document
        document_chunks = [
            doc for doc in document_store 
            if doc["notebook_id"] == request.notebook_id and doc["document_name"] == request.document_name
        ]
        
        if not document_chunks:
            # If no chunks found, let's see what documents are available
            available_docs = set()
            for doc in document_store:
                if doc["notebook_id"] == request.notebook_id:
                    available_docs.add(doc["document_name"])
            print(f"Available documents for notebook {request.notebook_id}: {available_docs}")
            raise HTTPException(status_code=404, detail=f"Document '{request.document_name}' not found. Available documents: {list(available_docs)}")
        
        print(f"Found {len(document_chunks)} chunks for document '{request.document_name}'")
        
        # Create summary from first 5 chunks to get good document overview
        summary_text = ""
        for chunk in document_chunks[:5]:
            chunk_text = chunk.get("chunk") or chunk.get("content", "")
            summary_text += chunk_text + "\n\n"
        
        # Limit summary length for the prompt
        if len(summary_text) > 2000:
            summary_text = summary_text[:2000] + "..."
        
        print(f"Got document summary: {len(summary_text)} characters from {len(document_chunks)} chunks")
        
        # Step 2: Ask Groq to generate YouTube search query
        video_query_prompt = f"""Based on this document content, create an optimal YouTube search query to find educational videos, tutorials, or explanations about the main topics:

{summary_text}

Create a search query that would find helpful YouTube videos for someone learning about these topics. Focus on the main concepts, subjects, or skills mentioned.

Respond with only a search query (2-8 words, good for YouTube):"""
        
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": video_query_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=50
        )
        
        search_query = completion.choices[0].message.content.strip().strip('"')
        print(f"Generated video search query: {search_query}")
        
        # Step 3: Search YouTube using Serper API
        search_url = "https://google.serper.dev/videos"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        
        search_payload = {
            "q": f"{search_query} site:youtube.com",
            "num": 15  # Get more results for variety
        }
        
        print(f"Searching videos with query: {search_query}")
        
        response = requests.post(search_url, json=search_payload, headers=headers)
        videos = []
        
        if response.status_code == 200:
            search_results = response.json()
            
            # Process video results
            if "videos" in search_results:
                for video in search_results["videos"][:12]:  # Limit to 12 videos
                    # Extract YouTube video ID from URL
                    video_url = video.get("link", "")
                    video_id = ""
                    
                    if "youtube.com/watch?v=" in video_url:
                        video_id = video_url.split("watch?v=")[1].split("&")[0]
                    elif "youtu.be/" in video_url:
                        video_id = video_url.split("youtu.be/")[1].split("?")[0]
                    
                    if video_id:
                        videos.append({
                            "title": video.get("title", ""),
                            "url": video_url,
                            "videoId": video_id,
                            "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                            "duration": video.get("duration", ""),
                            "date": video.get("date", ""),
                            "source": video.get("source", "YouTube")
                        })
        else:
            print(f"Serper API failed with status {response.status_code}")
            # Instead of hardcoded fallbacks, return an informative message
            videos = []
            
            # Add a message to chat about the search attempt
            notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
            if notebook:
                if "chat_history" not in notebook:
                    notebook["chat_history"] = []
                
                notebook["chat_history"].append({
                    "id": f"{len(notebook['chat_history']) + 1}-u",
                    "role": "user", 
                    "content": f"🎥 Video Search: {request.document_name}",
                    "timestamp": datetime.now().isoformat()
                })
                
                notebook["chat_history"].append({
                    "id": f"{len(notebook['chat_history']) + 1}-a", 
                    "role": "assistant",
                    "content": f"<h2>🎥 Video Search Results</h2><p>I searched for videos about '{search_query}' but couldn't retrieve results at the moment due to API limitations.</p><p><strong>Suggested search terms for YouTube:</strong> {search_query}</p><p>You can manually search YouTube using these terms to find relevant educational videos.</p>",
                    "timestamp": datetime.now().isoformat()
                })
            
            return VideoSearchResponse(
                success=False,
                query=search_query,
                videos=[],
                message=f"Video search temporarily unavailable. Suggested search: '{search_query}'"
            )
        
        print(f"Found {len(videos)} videos")
        
        # Step 4: Add video search results to chat history (avoid duplicates)
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if notebook:
            # Ensure notebook has chat_history
            if "chat_history" not in notebook:
                notebook["chat_history"] = []
            
            # Check if we already have a recent video search for this document
            recent_video_search = False
            for message in notebook["chat_history"][-5:]:  # Check last 5 messages
                if (message.get("content", "").startswith("🎥 Video Search:") and 
                    request.document_name in message.get("content", "")):
                    recent_video_search = True
                    break
            
            # Only add to chat history if no recent video search for this document
            if not recent_video_search:
                # Add user message for the video search action
                notebook["chat_history"].append({
                    "id": f"{len(notebook['chat_history']) + 1}-u",
                    "role": "user", 
                    "content": f"🎥 Video Search: {request.document_name}",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Add bot response with the video results
                video_list_html = "<ul>"
                for video in videos[:5]:  # Show first 5 in chat
                    video_list_html += f"<li><strong>{video['title']}</strong> - {video['duration']}</li>"
                video_list_html += "</ul>"
                
                notebook["chat_history"].append({
                    "id": f"{len(notebook['chat_history']) + 1}-a", 
                    "role": "assistant",
                    "content": f"<h2> Video Results for {request.document_name}</h2><p><strong>Search Query:</strong> {search_query}</p><p>Found {len(videos)} educational videos:</p>{video_list_html}<p><em>Click the Videos button to view all results with thumbnails and play them!</em></p>",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                print(f"Skipping chat history update - recent video search already exists for {request.document_name}")
        
        return VideoSearchResponse(
            success=True,
            query=search_query,
            videos=videos,
            message=f"Found {len(videos)} videos for '{search_query}'"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Video search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video search failed: {str(e)}")

@app.post("/visual-podcast", response_model=VisualPodcastResponse)
async def generate_visual_podcast(request: VisualPodcastRequest):
    """Generate visual podcast slides by overlaying text on template image for a document"""
    try:
        print(f"Starting visual podcast generation for document: {request.document_name}, notebook: {request.notebook_id}")
        
        # Step 1: Get document chunks directly from document_store (no similarity search needed)
        if not document_store:
            raise HTTPException(status_code=404, detail="No documents found. Please upload and process a PDF first.")
        
        # Get ALL chunks for the specific document
        document_chunks = [
            doc for doc in document_store 
            if doc["notebook_id"] == request.notebook_id and doc["document_name"] == request.document_name
        ]
        
        if not document_chunks:
            # If no chunks found, let's see what documents are available
            available_docs = set()
            for doc in document_store:
                if doc["notebook_id"] == request.notebook_id:
                    available_docs.add(doc["document_name"])
            print(f"Available documents for notebook {request.notebook_id}: {available_docs}")
            raise HTTPException(status_code=404, detail=f"Document '{request.document_name}' not found. Available documents: {list(available_docs)}")
        
        print(f"Found {len(document_chunks)} chunks for document '{request.document_name}'")
        
        # Create comprehensive summary from document chunks
        document_content = ""
        for chunk in document_chunks[:8]:  # Use 8 chunks for better context
            chunk_text = chunk.get("chunk") or chunk.get("content", "")
            document_content += chunk_text + "\n\n"
        
        # Limit content length for the prompt
        if len(document_content) > 3000:
            document_content = document_content[:3000] + "..."
        
        print(f"Got document content: {len(document_content)} characters from {len(document_chunks)} chunks")
        
        # Step 2: Ask Groq to generate slide content prompts
        slide_prompt = f"""Based on this document content, create content for 5-6 professional presentation slides that would make an engaging visual podcast.

Document Content:
{document_content}

For each slide, provide:
1. A clear, engaging title (8-12 words max)
2. 5-6 concise bullet points (each 8-12 words max for detailed content)
3. Content for text overlay on template image

IMPORTANT: Respond with ONLY a valid JSON array, no additional text or explanation.

Format your response exactly like this:
[
  {{
    "slide_number": 1,
    "title": "Introduction to [Main Topic]",
    "bullet_points": [
      "Key concept overview",
      "Main benefits explained", 
      "Real-world applications",
      "Why this matters today",
      "Future implications and opportunities",
      "Getting started with implementation"
    ],
    "image_prompt": "Create a single professional presentation slide. Title: '[Title]'. Bullet Points: [bullet points]. Background: Clean, modern, light gradient (blue/white). Style: Minimalist, like a PowerPoint slide. Include icons/illustrations next to each bullet point. Ensure it looks like a slide screenshot, not a poster."
  }}
]

Create slides that tell a complete story about the document's main topics. Return only the JSON array."""

        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": slide_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=2000
        )
        
        response_text = completion.choices[0].message.content.strip()
        print(f"Generated slide content: {response_text[:200]}...")
        
        # Parse the JSON response - extract JSON from the response if it contains other text
        try:
            # First try to parse the response directly
            try:
                slides_data = json.loads(response_text)
            except json.JSONDecodeError:
                # If direct parsing fails, try to extract JSON from the response
                import re
                
                # Look for JSON array pattern
                json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                    slides_data = json.loads(json_text)
                else:
                    # Try to find JSON starting with [ and ending with ]
                    start_idx = response_text.find('[')
                    end_idx = response_text.rfind(']')
                    
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        json_text = response_text[start_idx:end_idx + 1]
                        slides_data = json.loads(json_text)
                    else:
                        raise ValueError("No valid JSON array found in response")
            
            if not isinstance(slides_data, list):
                raise ValueError("Response is not a list")
                
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse slide content JSON: {e}")
            print(f"Full response text: {response_text}")
            
            # Fallback: create manual slides based on the document content
            print("Creating fallback slides from document content...")
            slides_data = [
                {
                    "slide_number": 1,
                    "title": f"Overview of {request.document_name.replace('.pdf', '')}",
                    "bullet_points": [
                        "Key document highlights",
                        "Main topics covered",
                        "Essential information",
                        "Important takeaways"
                    ],
                    "image_prompt": f"Create a single professional presentation slide. Title: 'Overview of {request.document_name.replace('.pdf', '')}'. Bullet Points: Key document highlights, Main topics covered, Essential information, Important takeaways. Background: Clean, modern, light gradient (blue/white). Style: Minimalist, like a PowerPoint slide. Include icons/illustrations next to each bullet point. Ensure it looks like a slide screenshot, not a poster."
                }
            ]
        
        # Step 3: Generate slides by overlaying text on template image
        generated_slides = []
        
        for i, slide_data in enumerate(slides_data[:6]):  # Limit to 6 slides
            try:
                print(f"Generating image for slide {i+1}: {slide_data.get('title', 'Untitled')}")
                
                # Extract slide information
                title = slide_data.get("title", f"Slide {i+1}")
                bullet_points = slide_data.get("bullet_points", [])
                image_prompt = slide_data.get("image_prompt", "")
                
                # If no image prompt provided, create an enhanced one based on document type
                if not image_prompt:
                    bullet_text = "\n".join([f"• {point}" for point in bullet_points])
                    
                    # Analyze document type to create appropriate image prompts
                    doc_name_lower = request.document_name.lower()
                    doc_content_lower = document_content.lower()
                    
                    # Determine document type and appropriate visual style
                    if any(keyword in doc_name_lower for keyword in ['resume', 'cv', 'curriculum']) or \
                       any(keyword in doc_content_lower for keyword in ['experience', 'education', 'skills', 'employment', 'university', 'degree']):
                        document_type = "resume"
                        visual_style = "professional career infographic"
                        avoid_people = "STRICTLY NO human faces, portraits, or people images"
                    elif any(keyword in doc_content_lower for keyword in ['research', 'study', 'analysis', 'methodology', 'findings']):
                        document_type = "research"
                        visual_style = "academic research visualization"
                        avoid_people = "NO human subjects, focus on data and concepts"
                    elif any(keyword in doc_content_lower for keyword in ['business', 'company', 'strategy', 'market', 'revenue']):
                        document_type = "business"
                        visual_style = "business strategy diagram"
                        avoid_people = "NO portraits, use professional business graphics"
                    elif any(keyword in doc_content_lower for keyword in ['technical', 'development', 'programming', 'software', 'code']):
                        document_type = "technical"
                        visual_style = "technical architecture diagram"
                        avoid_people = "NO human images, focus on technical concepts"
                    else:
                        document_type = "general"
                        visual_style = "professional infographic"
                        avoid_people = "NO human faces or portraits"
                    
                    # Create dynamic, context-aware image prompt
                    image_prompt = f"""Create a professional {visual_style} representing: "{title}"

DOCUMENT CONTEXT: {document_type.upper()} document
VISUAL CONCEPT: {title}
KEY THEMES: {', '.join(bullet_points[:3])}

DESIGN REQUIREMENTS:
• Style: Clean, modern {visual_style}
• Elements: Icons, symbols, charts, diagrams, flowcharts
• Colors: Professional blue/white gradient or corporate theme
• Composition: Balanced layout with clear visual hierarchy
• Quality: High-resolution, presentation-ready
• Focus: Abstract concepts through visual metaphors

STRICT REQUIREMENTS:
• {avoid_people}
• NO text generation (avoid spelling errors)
• NO complex written content
• Use symbols, icons, and diagrams only
• If showing progression/timeline, use abstract elements
• For skills/education: use graduation caps, books, certificates (NOT people)
• For business: use charts, graphs, building icons (NOT executives)
• For technical: use code symbols, gear icons, network diagrams

PREFERRED ELEMENTS:
• Professional icons and symbols
• Clean geometric shapes
• Infographic-style layouts
• Abstract representations of concepts
• Corporate design elements
• Charts and diagrams where appropriate

Create a visually compelling {visual_style} that represents the concept through professional imagery and symbols, NOT human subjects."""

                # Generate image using PIL text embedding on template
                try:
                    print(f"Embedding text on template for slide {i+1} with title: {title}")
                    
                    # Import required modules
                    from PIL import Image, ImageDraw, ImageFont
                    
                    # Load the template image
                    template_path = Path("public/ppt_temp.png")
                    if not template_path.exists():
                        # Fallback to current directory
                        template_path = Path("ppt_temp.png")
                        if not template_path.exists():
                            print(f"Template image not found for slide {i+1}")
                            continue
                    
                    # Open template and create a copy
                    template_image = Image.open(template_path).convert('RGB')
                    img_width, img_height = template_image.size
                    print(f"Template image loaded successfully: {img_width}x{img_height}")
                    
                    # Create a drawing context
                    draw = ImageDraw.Draw(template_image)
                    
                    # Try to load fonts (fallback to default if not available)
                    try:
                        # Try to load Arial fonts for Windows
                        title_font = ImageFont.truetype("arial.ttf", 48)
                        bullet_font = ImageFont.truetype("arial.ttf", 32)
                    except:
                        try:
                            # Fallback to other common fonts
                            title_font = ImageFont.truetype("Arial.ttf", 48)
                            bullet_font = ImageFont.truetype("Arial.ttf", 32)
                        except:
                            # Use default font as last resort
                            title_font = ImageFont.load_default()
                            bullet_font = ImageFont.load_default()
                            print("Using default font (fonts not found)")
                    
                    # Calculate positions based on image dimensions
                    # Title at top (15% from top), bullets at middle-bottom area
                    center_x = img_width // 2
                    title_y = int(img_height * 0.15)  # 15% from top for title
                    
                    # Title position (centered)
                    title_bbox = draw.textbbox((0, 0), title, font=title_font)
                    title_width = title_bbox[2] - title_bbox[0]
                    title_x = center_x - (title_width // 2)
                    
                    # Draw title text
                    draw.text((title_x, title_y), title, fill=(0, 0, 0), font=title_font)
                    print(f"Drew title: {title} at ({title_x}, {title_y})")
                    
                    # Bullet points start much lower with large gap from title
                    bullet_start_y = int(img_height * 0.35)  # Start at 35% from top (big gap from title)
                    bullet_spacing = 60  # Larger space between bullets (increased from 50)
                    
                    # Draw bullet points (up to 6, centered)
                    for idx, point in enumerate(bullet_points[:6]):  # Show up to 6 bullets
                        bullet_y = bullet_start_y + (idx * bullet_spacing)
                        bullet_text = f"• {point}"
                        
                        # Center each bullet point
                        bullet_bbox = draw.textbbox((0, 0), bullet_text, font=bullet_font)
                        bullet_width = bullet_bbox[2] - bullet_bbox[0]
                        bullet_x = center_x - (bullet_width // 2)
                        
                        draw.text((bullet_x, bullet_y), bullet_text, fill=(0, 0, 0), font=bullet_font)
                        print(f"Drew bullet {idx+1}: {point} at ({bullet_x}, {bullet_y})")
                    
                    # Save the generated slide
                    images_dir = Path("data/generated_images")
                    images_dir.mkdir(parents=True, exist_ok=True)
                    
                    image_filename = f"slide_{request.notebook_id}_{i+1}_{uuid.uuid4().hex[:8]}.png"
                    image_path = images_dir / image_filename
                    template_image.save(image_path)
                    
                    # Create URL for frontend access
                    image_url = f"http://localhost:8001/images/{image_filename}"
                    print(f"Saved slide image: {image_path}")
                    
                except Exception as pil_error:
                    print(f"PIL text embedding error for slide {i+1}: {type(pil_error).__name__}: {pil_error}")
                    # Continue with next slide instead of failing completely
                    continue
                
                if image_url:
                    # Step 3.5: Generate TTS audio for this slide
                    audio_url = None
                    try:
                        print(f"Generating TTS audio for slide {i+1}")
                        
                        # Generate natural narration using Groq - longer since we're using Edge TTS (no API limits)
                        narration_prompt = f"""Create a natural, engaging narration for this presentation slide. Since we're using unlimited Edge TTS, you can be more detailed and conversational.

Slide: {title}
Key Points: {', '.join(bullet_points)}
Document Context: {document_content[:300]}...

Requirements:
- Write a natural, conversational explanation (50-80 words)
- Sound like a professional presenter, not robotic
- Explain the significance and context of the information
- Connect ideas in a flowing narrative
- Use engaging language that holds attention
- Include insights and implications where relevant

Example good style: "Let's explore John's technical expertise, which forms the backbone of his professional profile. His proficiency in Python, Java, and machine learning frameworks demonstrates not just coding ability, but a deep understanding of modern technology stacks that drive today's digital innovation."

Return only the narration text, no formatting."""

                        narration_completion = client.chat.completions.create(
                            messages=[{"role": "user", "content": narration_prompt}],
                            model="llama-3.1-8b-instant",
                            temperature=0.7,
                            max_tokens=300  # Increased for longer narrations
                        )
                        
                        narration_text = narration_completion.choices[0].message.content.strip()
                        
                        # Clean up the narration text
                        narration_text = narration_text.replace('"', '').replace("'", "").strip()
                        
                        # No trimming needed since Edge TTS has no limits
                        print(f"Generated narration for slide {i+1} ({len(narration_text)} chars): {narration_text}")
                        
                        # Generate audio using Edge TTS only
                        audio_generated = False
                        
                        try:
                            print(f"Using Edge TTS for slide {i+1}")
                            
                            # Create unique audio filename (use .mp3 for Edge TTS)
                            audio_filename = f"slide_{request.notebook_id}_{i+1}_{uuid.uuid4().hex[:8]}.mp3"
                            audio_path = images_dir / audio_filename
                            
                            # Generate speech using Edge TTS with Jenny Neural voice
                            tts = edge_tts.Communicate(narration_text, voice="en-US-JennyNeural")
                            
                            # Use asyncio.run in a thread to avoid event loop conflicts
                            def run_edge_tts():
                                import asyncio
                                # Set a proper event loop policy for Windows
                                if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
                                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                                asyncio.run(tts.save(str(audio_path)))
                            
                            # Run in a separate thread to avoid event loop conflicts
                            thread = threading.Thread(target=run_edge_tts)
                            thread.start()
                            thread.join()
                            
                            # Create URL for frontend access
                            audio_url = f"http://localhost:8001/images/{audio_filename}"
                            print(f"✅ Saved Edge TTS audio (JennyNeural): {audio_path}")
                            audio_generated = True
                            
                        except Exception as edge_tts_error:
                            print(f"Edge TTS error for slide {i+1}: {edge_tts_error}")
                            audio_url = None
                        
                        if not audio_generated:
                            print(f"❌ Edge TTS failed for slide {i+1}")
                            audio_url = None
                            
                    except Exception as tts_error:
                        print(f"TTS generation error for slide {i+1}: {tts_error}")
                        audio_url = None
                    
                    generated_slides.append(SlideData(
                        title=title,
                        bullet_points=bullet_points,
                        image_url=image_url,
                        audio_url=audio_url,
                        slide_number=i+1
                    ))
                else:
                    print(f"Failed to generate image for slide {i+1}")
                    
            except Exception as e:
                print(f"Error generating slide {i+1}: {str(e)}")
                continue
        
        if not generated_slides:
            raise HTTPException(status_code=500, detail="Failed to generate any slides")
        
        print(f"Successfully generated {len(generated_slides)} slides")
        
        # Step 4: Add visual podcast results to chat history
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if notebook:
            # Ensure notebook has chat_history
            if "chat_history" not in notebook:
                notebook["chat_history"] = []
            
            # Add user message for the visual podcast action
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-u",
                "role": "user", 
                "content": f"🎬 Visual Podcast: {request.document_name}",
                "timestamp": datetime.now().isoformat()
            })
            
            # Add bot response with the visual podcast results
            slides_html = "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-top: 16px;'>"
            for slide in generated_slides[:3]:  # Show first 3 in chat
                slides_html += f"""
                <div style='border: 1px solid #ddd; border-radius: 8px; padding: 12px; background: #f9f9f9;'>
                    <h4 style='margin: 0 0 8px 0; color: #333;'>{slide.title}</h4>
                    <ul style='margin: 0; padding-left: 20px; color: #666;'>
                """
                for point in slide.bullet_points:
                    slides_html += f"<li>{point}</li>"
                slides_html += "</ul></div>"
            slides_html += "</div>"
            
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-a", 
                "role": "assistant",
                "content": f"<h2>🎬 Visual Podcast Generated</h2><p><strong>Document:</strong> {request.document_name}</p><p>Created {len(generated_slides)} professional presentation slides perfect for a visual podcast!</p>{slides_html}<p><em>Click the Visual Podcast button to view all slides with full images and audio!</em></p>",
                "timestamp": datetime.now().isoformat()
            })
        
        # Step 5: Generate MP4 video combining slides and audio
        video_url = None
        try:
            print("Creating MP4 video from slides and audio...")
            
            video_clips = []
            
            for slide in generated_slides:
                # Get image path
                image_filename = slide.image_url.split('/')[-1]
                image_path = Path("data/generated_images") / image_filename
                
                if image_path.exists():
                    print(f"Processing slide {slide.slide_number}: {image_path}")
                    
                    # Create image clip
                    img_clip = mp.ImageClip(str(image_path))
                    
                    # Set duration and add audio if available
                    if slide.audio_url:
                        audio_filename = slide.audio_url.split('/')[-1]
                        audio_path = Path("data/generated_images") / audio_filename
                        
                        if audio_path.exists():
                            try:
                                print(f"Adding audio: {audio_path}")
                                audio_clip = mp.AudioFileClip(str(audio_path))
                                # Set image duration to match audio length (minimum 3 seconds)
                                duration = max(audio_clip.duration, 3.0)
                                img_clip = img_clip.set_duration(duration).set_audio(audio_clip)
                                print(f"Slide {slide.slide_number} duration: {duration}s")
                            except Exception as audio_error:
                                print(f"Error adding audio to slide {slide.slide_number}: {audio_error}")
                                # Fallback to 5 seconds without audio
                                img_clip = img_clip.set_duration(5.0)
                        else:
                            print(f"Audio file not found: {audio_path}")
                            img_clip = img_clip.set_duration(5.0)
                    else:
                        # No audio, set default duration
                        img_clip = img_clip.set_duration(5.0)
                    
                    video_clips.append(img_clip)
                else:
                    print(f"Image not found for slide {slide.slide_number}: {image_path}")
            
            if video_clips:
                print(f"Concatenating {len(video_clips)} video clips...")
                # Concatenate all clips
                final_video = mp.concatenate_videoclips(video_clips, method="compose")
                
                # Save video
                video_filename = f"visual_podcast_{request.notebook_id}_{uuid.uuid4().hex[:8]}.mp4"
                video_path = Path("data/generated_images") / video_filename
                
                print(f"Writing video to: {video_path}")
                final_video.write_videofile(
                    str(video_path),
                    fps=24,
                    audio_codec='aac',
                    codec='libx264',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True,
                    verbose=False,
                    logger=None
                )
                
                video_url = f"http://localhost:8001/images/{video_filename}"
                print(f"✅ Video created successfully: {video_path}")
                print(f"🎬 Video URL: {video_url}")
                
                # Close clips to free memory
                final_video.close()
                for clip in video_clips:
                    clip.close()
            else:
                print("❌ No video clips created - video generation skipped")
                
        except Exception as video_error:
            print(f"❌ Video generation error: {video_error}")
            import traceback
            traceback.print_exc()
            video_url = None
        
        # Add video to chat history if successfully generated
        if video_url and notebook:
            video_message_content = f"""
            <div style='border: 2px solid #4CAF50; border-radius: 12px; padding: 16px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); margin: 16px 0;'>
                <h3 style='margin: 0 0 12px 0; color: #2E7D32; display: flex; align-items: center;'>
                    🎬 Visual Podcast Video Ready
                </h3>
                <p style='margin: 0 0 12px 0; color: #555;'>
                    <strong>Document:</strong> {request.document_name}<br>
                    <strong>Duration:</strong> {len(generated_slides)} slides<br>
                    <strong>Format:</strong> MP4 with narration
                </p>
                <div style='text-align: center;'>
                    <video controls style='max-width: 100%; max-height: 400px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);'>
                        <source src='{video_url}' type='video/mp4'>
                        Your browser does not support the video tag.
                    </video>
                </div>
                <p style='margin: 12px 0 0 0; font-size: 14px; color: #777; text-align: center;'>
                    <em>Click play to watch your visual podcast!</em>
                </p>
            </div>
            """
            
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-a", 
                "role": "assistant",
                "content": video_message_content,
                "timestamp": datetime.now().isoformat()
            })
            
            # Save the updated notebook
            save_notebooks()
        
        return VisualPodcastResponse(
            success=True,
            slides=generated_slides,
            total_slides=len(generated_slides),
            video_url=video_url,
            message=f"Generated {len(generated_slides)} slides" + (" with video" if video_url else "") + " for visual podcast"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Visual podcast generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Visual podcast generation failed: {str(e)}")

@app.get("/images/{filename}")
async def serve_generated_image(filename: str):
    """Serve generated slide images, audio files, and videos"""
    try:
        images_dir = Path("data/generated_images")
        file_path = images_dir / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine media type based on file extension
        file_extension = file_path.suffix.lower()
        if file_extension in ['.png', '.jpg', '.jpeg']:
            media_type = "image/png" if file_extension == '.png' else "image/jpeg"
        elif file_extension in ['.mp3', '.wav']:
            media_type = "audio/mpeg" if file_extension == '.mp3' else "audio/wav"
        elif file_extension == '.mp4':
            media_type = "video/mp4"
        else:
            media_type = "application/octet-stream"
        
        # Read the file
        with open(file_path, "rb") as file:
            file_data = file.read()
        
        # Return file with appropriate headers for download
        headers = {
            "Cache-Control": "max-age=3600",
        }
        
        # Add content-disposition header for video files to enable proper download
        if file_extension == '.mp4':
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=media_type,
            headers=headers
        )
        
    except Exception as e:
        print(f"Error serving image: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to serve image")

@app.post("/generate-chat-pdf")
async def generate_chat_pdf(request: ChatPDFRequest):
    """Generate a PDF of the chat history for a notebook"""
    try:
        # Get notebook
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        
        chat_history = notebook.get("chat_history", [])
        if not chat_history:
            raise HTTPException(status_code=400, detail="No chat history available")
        
        # First, clean up any problematic characters in the chat history
        for i, msg in enumerate(chat_history):
            if "content" in msg and msg["content"]:
                content = msg["content"]
                
                # Strip HTML if found
                if "<" in content and ">" in content:
                    try:
                        # Try to parse with BeautifulSoup and extract text
                        soup = BeautifulSoup(content, "html.parser")
                        content = soup.get_text(separator="\n")
                    except Exception as e:
                        print(f"Error parsing HTML with BeautifulSoup: {e}")
                        # Fallback to regex
                        content = re.sub(r'</?[^>]+>', '', content)
                
                # Replace problematic characters
                content = content.replace('\uf0a7', '*')  # Replace Unicode bullets
                content = content.replace('\uf0b7', '*')  # Replace Unicode bullets
                content = content.replace('\u25a0', ' ')  # Replace black boxes
                content = content.replace('\u25a1', ' ')  # Replace white boxes
                content = content.replace('■', ' ')      # Replace black boxes
                content = content.replace('□', ' ')      # Replace white boxes
                
                # Replace any other non-standard characters
                chat_history[i]["content"] = ''.join(c if ord(c) < 128 else ' ' for c in content)
        
        # Create a PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter,
            leftMargin=1*inch, 
            rightMargin=1*inch,
            topMargin=1*inch, 
            bottomMargin=1*inch
        )
        
        # Define basic styles
        styles = getSampleStyleSheet()
        
        # Simple styles
        title_style = styles['Title']
        subtitle_style = styles['Italic']
        normal_style = styles['Normal']
        heading_style = styles['Heading2']
        
        # Create the PDF content
        elements = []
        
        # Add title
        elements.append(Paragraph(f"DocFox Chat: {notebook['title']}", title_style))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
        elements.append(Spacer(1, 0.5*inch))
        
        # Get a clean formatted version of the chat
        formatted_text = format_chat_for_pdf(chat_history)
        
        # Split into paragraphs and process
        paragraphs = formatted_text.split('\n')
        
        for p in paragraphs:
            # Skip empty lines with spacing
            if not p.strip():
                elements.append(Spacer(1, 0.1*inch))
                continue
            
            # Strip any remaining HTML tags
            p = re.sub(r'</?[^>]+>', '', p)
            
            # Headers for user/AI messages
            if p == "User Message:" or p.startswith("User Message:"):
                elements.append(Spacer(1, 0.3*inch))
                elements.append(Paragraph(p, heading_style))
            elif p == "DocFox Response:" or p.startswith("DocFox Response:"):
                elements.append(Spacer(1, 0.3*inch))
                elements.append(Paragraph(p, heading_style))
            # Separator lines
            elif p.startswith("-----"):
                elements.append(Spacer(1, 0.1*inch))
            # Regular content
            else:
                # Clean up any remaining black box characters
                p = p.replace('\u25a0', ' ').replace('\u25a1', ' ')
                # Replace any non-ASCII characters with spaces
                p = ''.join(c if ord(c) < 128 else ' ' for c in p)
                # Replace special characters for XML
                p = p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                elements.append(Paragraph(p, normal_style))
        
        # Build the PDF
        doc.build(elements)
        
        # Reset buffer position
        buffer.seek(0)
        
        # Return the PDF
        return StreamingResponse(
            buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={notebook['title'].replace(' ', '_')}_chat.pdf"}
        )
        
    except Exception as e:
        print(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

def clean_scraped_text(text: str) -> str:
    """Clean scraped website text by removing excessive whitespace and newlines"""
    if not text:
        return ""
    
    # Replace multiple newlines with spaces
    text = re.sub(r'\n+', ' ', text)
    # Replace multiple whitespace characters with single space
    text = re.sub(r'\s+', ' ', text)
    # Remove excessive special characters
    text = re.sub(r'[^\w\s.,;:!?()-]', ' ', text)
    # Clean up extra spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def chunk_text_by_characters(text: str, max_chars: int = 2000, overlap_chars: int = 200) -> List[str]:
    """Chunk text based on character count with overlap for better context preservation"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chars
        
        # If we're not at the end of the text, try to break at a sentence or word boundary
        if end < len(text):
            # Look for sentence endings first
            sentence_end = text.rfind('.', start, end)
            if sentence_end == -1:
                sentence_end = text.rfind('!', start, end)
            if sentence_end == -1:
                sentence_end = text.rfind('?', start, end)
            
            # If no sentence ending found, look for word boundaries
            if sentence_end == -1:
                word_break = text.rfind(' ', start, end)
                if word_break != -1:
                    end = word_break
            else:
                end = sentence_end + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position with overlap
        start = end - overlap_chars if end < len(text) else end
        
        # Prevent infinite loop
        if start >= len(text):
            break
    
    return chunks

async def process_website_content(content: str, title: str, notebook_id: int):
    """Process website content for RAG system with improved text cleaning and chunking"""
    try:
        # Clean the scraped text
        cleaned_content = clean_scraped_text(content)
        
        if not cleaned_content:
            print("No content to process after cleaning")
            return
        
        print(f"Processing website content: {len(cleaned_content)} characters")
        
        # Chunk the content using character-based chunking (smaller chunks for dense content)
        chunks = chunk_text_by_characters(cleaned_content, max_chars=1000, overlap_chars=100)
        
        print(f"Created {len(chunks)} chunks from website content")
        
        # Generate embeddings for each chunk
        global document_store, faiss_index
        
        for i, chunk in enumerate(chunks):
            try:
                # Generate embedding
                embedding = embedding_model.encode([chunk])
                
                # Add to FAISS index
                faiss_index.add(embedding.astype(np.float32))
                
                # Store metadata
                document_store.append({
                    "id": len(document_store),
                    "notebook_id": notebook_id,
                    "document_name": title,
                    "chunk": chunk,
                    "chunk_index": i,
                    "source": f"website_{notebook_id}",
                    "type": "website"
                })
                
            except Exception as chunk_error:
                print(f"Error processing chunk {i}: {chunk_error}")
                continue
        
        print(f"Successfully processed {len(chunks)} chunks for website: {title}")
        
    except Exception as e:
        print(f"Error processing website content: {e}")
        import traceback
        traceback.print_exc()

@app.post("/scrape-website", response_model=WebsiteScrapeResponse)
async def scrape_website(request: WebsiteScrapeRequest):
    """Scrape a website and create a new notebook with the content"""
    try:
        print(f"Starting website scraping for URL: {request.url}")
        
        # Scrape the website using Firecrawl
        try:
            scrape_result = firecrawl_client.scrape(request.url)
            print(f"Firecrawl result type: {type(scrape_result)}")
        except Exception as firecrawl_error:
            print(f"Firecrawl error: {firecrawl_error}")
            raise HTTPException(status_code=400, detail=f"Firecrawl error: {str(firecrawl_error)}")
        
        if not scrape_result:
            raise HTTPException(status_code=400, detail="Firecrawl returned empty result")
        
        # Handle Firecrawl v2 Document object
        content = ""
        title = f"Website: {request.url}"
        
        if hasattr(scrape_result, 'markdown') and scrape_result.markdown:
            content = scrape_result.markdown
        elif hasattr(scrape_result, 'html') and scrape_result.html:
            content = scrape_result.html
        elif isinstance(scrape_result, dict) and 'content' in scrape_result:
            content = scrape_result.get('content', '')
        else:
            print(f"Unexpected scrape result structure: {scrape_result}")
            raise HTTPException(status_code=400, detail="Failed to extract content from scraped website")
        
        # Get title from metadata if available
        if hasattr(scrape_result, 'metadata') and scrape_result.metadata:
            if hasattr(scrape_result.metadata, 'title') and scrape_result.metadata.title:
                title = scrape_result.metadata.title
        
        print(f"Extracted content length: {len(content)}")
        print(f"Extracted title: {title}")
        
        if not content or len(content.strip()) == 0:
            raise HTTPException(status_code=400, detail="No content found on the website")
        
        # Create a new notebook
        global next_notebook_id, notebooks_storage, next_page_id
        
        notebook_id = next_notebook_id
        next_notebook_id += 1
        
        page_id = next_page_id
        next_page_id += 1
        
        # Clean the content for storage
        cleaned_content = clean_scraped_text(content)
        
        # Create the notebook
        new_notebook = {
            "id": notebook_id,
            "title": title,
            "pages": [{
                "id": page_id,
                "title": f"Content from {request.url}",
                "content": cleaned_content,
                "filename": f"website_{notebook_id}.txt",
                "type": "website",
                "created_at": datetime.now().isoformat()
            }],
            "created_at": datetime.now().isoformat()
        }
        
        notebooks_storage.append(new_notebook)
        
        # Process the content for RAG
        await process_website_content(content, title, notebook_id)
        
        print(f"Website scraped successfully. Created notebook {notebook_id} with page {page_id}")
        
        return WebsiteScrapeResponse(
            success=True,
            title=title,
            content=cleaned_content[:1000] + "..." if len(cleaned_content) > 1000 else cleaned_content,
            url=request.url,
            notebook_id=notebook_id,
            page_id=page_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Website scraping error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to scrape website: {str(e)}")

@app.delete("/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: int):
    global notebooks_storage
    notebook = next((nb for nb in notebooks_storage if nb["id"] == notebook_id), None)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    notebooks_storage = [nb for nb in notebooks_storage if nb["id"] != notebook_id]
    save_notebooks()  # Persist the deletion
    return {"message": "Notebook deleted successfully"}

# ===== QUIZ ENDPOINTS =====

@app.post("/quiz/generate")
async def generate_quiz(request: QuizGenerateRequest):
    """
    Generate quiz questions from uploaded documents using RAG.
    """
    try:
        print(f"\n[QUIZ] === Generate Quiz Request ===")
        print(f"[QUIZ] notebook_id: {request.notebook_id}")
        print(f"[QUIZ] num_questions: {request.num_questions}")
        print(f"[QUIZ] FAISS index total: {faiss_index.ntotal}")
        print(f"[QUIZ] Document store size: {len(document_store)}")
        
        if faiss_index.ntotal == 0:
            raise HTTPException(status_code=400, detail="No documents uploaded yet. Please upload and process a PDF first.")
        
        # Check if notebook exists and has documents
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if not notebook:
            print(f"[QUIZ] ERROR: Notebook {request.notebook_id} not found")
            print(f"[QUIZ] Available notebooks: {[nb['id'] for nb in notebooks_storage]}")
            raise HTTPException(status_code=404, detail="Notebook not found")
        
        print(f"[QUIZ] Found notebook: {notebook['title']}")
        
        # Check if notebook has processed documents
        notebook_docs = [doc for doc in document_store if doc["notebook_id"] == request.notebook_id]
        print(f"[QUIZ] Found {len(notebook_docs)} documents for notebook {request.notebook_id}")
        
        if not notebook_docs:
            # Debug: show what notebook_ids exist in document_store
            existing_notebook_ids = list(set([doc.get("notebook_id") for doc in document_store]))
            print(f"[QUIZ] ERROR: No documents for notebook {request.notebook_id}")
            print(f"[QUIZ] Existing notebook_ids in document_store: {existing_notebook_ids}")
            print(f"[QUIZ] Sample document: {document_store[0] if document_store else 'None'}")
            raise HTTPException(status_code=400, detail="No documents processed for this notebook yet.")
        
        print(f"[QUIZ] Calling quiz_system.generate_questions...")
        questions = quiz_system.generate_questions(
            notebook_id=request.notebook_id,
            document_store=document_store,
            faiss_index=faiss_index,
            num_questions=request.num_questions
        )
        
        print(f"[QUIZ] Successfully generated {len(questions)} questions")
        
        return {
            "questions": questions,
            "total_questions": len(questions),
            "message": "Quiz questions generated successfully"
        }
        
    except Exception as e:
        print(f"[QUIZ] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating quiz: {str(e)}")

@app.post("/quiz/select")
async def select_quiz_questions(request: QuizSelectRequest):
    """
    Select random questions from the generated quiz.
    """
    try:
        notebook_questions = quiz_system.get_questions_for_notebook(request.notebook_id)
        
        if not notebook_questions:
            raise HTTPException(status_code=400, detail="No questions generated yet. Please generate questions first.")
        
        selected = quiz_system.get_random_questions(request.notebook_id, request.num_questions)
        
        return {
            "questions": selected,
            "total_selected": len(selected)
        }
        
    except Exception as e:
        print(f"Error selecting questions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error selecting questions: {str(e)}")

@app.post("/quiz/evaluate", response_model=QuizEvaluationResponse)
async def evaluate_quiz_answer(request: QuizAnswerRequest):
    """
    Evaluate user's answer using RAG and similarity matching with Groq LLM.
    """
    try:
        if faiss_index.ntotal == 0:
            raise HTTPException(status_code=400, detail="No documents uploaded.")
        
        evaluation = quiz_system.evaluate_answer(
            question=request.question,
            user_answer=request.user_answer,
            notebook_id=request.notebook_id,
            document_store=document_store,
            embedding_model=embedding_model,
            faiss_index=faiss_index,
            question_id=request.question_id
        )
        
        return QuizEvaluationResponse(**evaluation)
        
    except Exception as e:
        print(f"Error evaluating answer: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error evaluating answer: {str(e)}")

@app.get("/quiz/status/{notebook_id}")
async def get_quiz_status(notebook_id: int):
    """
    Get the current quiz status for a specific notebook.
    """
    try:
        notebook_questions = quiz_system.get_questions_for_notebook(notebook_id)
        notebook_docs = [doc for doc in document_store if doc["notebook_id"] == notebook_id]
        
        return {
            "questions_generated": len(notebook_questions),
            "documents_loaded": len(set(doc["document_name"] for doc in notebook_docs)),
            "has_questions": len(notebook_questions) > 0,
            "notebook_id": notebook_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting quiz status: {str(e)}")

@app.delete("/quiz/clear/{notebook_id}")
async def clear_quiz(notebook_id: int):
    """
    Clear generated questions for a specific notebook.
    """
    try:
        quiz_system.clear_questions(notebook_id)
        return {"message": f"Quiz questions cleared for notebook {notebook_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing quiz: {str(e)}")

# Flashcard endpoints
@app.post("/flashcards/generate")
async def generate_flashcards(request: FlashcardGenerateRequest):
    """Generate flashcards from document content using RAG"""
    try:
        print(f"Generating {request.num_flashcards} flashcards for notebook {request.notebook_id}")
        
        if not document_store:
            raise HTTPException(status_code=404, detail="No documents found. Please upload and process a PDF first.")
        
        # Check if notebook has documents
        notebook_docs = [doc for doc in document_store if doc.get("notebook_id") == request.notebook_id]
        if not notebook_docs:
            raise HTTPException(status_code=404, detail=f"No documents found for notebook {request.notebook_id}")
        
        # Generate flashcards
        flashcards = flashcard_system.generate_flashcards(
            notebook_id=request.notebook_id,
            document_store=document_store,
            embedding_model=embedding_model,
            faiss_index=faiss_index,
            num_flashcards=request.num_flashcards
        )
        
        if not flashcards:
            raise HTTPException(status_code=500, detail="Failed to generate flashcards")
        
        return {
            "success": True,
            "flashcards": flashcards,
            "total_flashcards": len(flashcards),
            "message": f"Generated {len(flashcards)} flashcards successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating flashcards: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating flashcards: {str(e)}")

@app.get("/flashcards/status/{notebook_id}")
async def get_flashcard_status(notebook_id: int):
    """Get flashcard generation status"""
    try:
        status = flashcard_system.get_flashcard_status()
        return {
            "notebook_id": notebook_id,
            **status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting flashcard status: {str(e)}")

def _format_script_with_timestamps(script: str, total_duration: int) -> str:
    """Format podcast script with clickable timestamps"""
    # Split script into sections based on headers
    lines = script.split('\n')
    sections = []
    current_section = []
    
    for line in lines:
        if line.strip().startswith('##') or (line.strip() and len(line.strip()) < 100 and line.strip().isupper()):
            if current_section:
                sections.append('\n'.join(current_section))
            current_section = [line]
        else:
            if line.strip():
                current_section.append(line)
    
    if current_section:
        sections.append('\n'.join(current_section))
    
    if not sections or total_duration == 0:
        return f"<div style='white-space: pre-wrap;'>{script}</div>"
    
    # Calculate approximate timestamp for each section
    formatted_sections = []
    section_duration = total_duration / len(sections)
    
    for i, section in enumerate(sections):
        timestamp_seconds = int(i * section_duration)
        minutes = timestamp_seconds // 60
        seconds = timestamp_seconds % 60
        timestamp = f"{minutes}:{seconds:02d}"
        
        # Extract title if it's a header
        section_lines = section.split('\n')
        title = section_lines[0].replace('##', '').replace('#', '').strip()
        
        if len(title) > 80:
            title = title[:80] + "..."
        
        formatted_sections.append(f"""
            <div style='margin-bottom: 8px; padding: 6px; background: rgba(0, 0, 0, 0.2); border-radius: 3px; border-left: 2px solid #a855f7;'>
                <div style='display: flex; align-items: center; gap: 6px; margin-bottom: 3px;'>
                    <span class='timestamp-link' data-seconds='{timestamp_seconds}' 
                          style='cursor: pointer; background: rgba(168, 85, 247, 0.2); color: #a855f7; padding: 1px 6px; border-radius: 2px; font-size: 9px; font-weight: 600; font-family: monospace; transition: all 0.2s;'
                          onmouseover='this.style.background="rgba(168, 85, 247, 0.4)"'
                          onmouseout='this.style.background="rgba(168, 85, 247, 0.2)"'>
                        ▶ {timestamp}
                    </span>
                    <span style='font-weight: 600; color: #fff; font-size: 10px;'>{title}</span>
                </div>
                <div style='color: #d1d5db; font-size: 9px; line-height: 1.4; padding-left: 4px;'>
                    {section.replace(section_lines[0], '').strip()[:150]}{'...' if len(section.replace(section_lines[0], '').strip()) > 150 else ''}
                </div>
            </div>
        """)
    
    return ''.join(formatted_sections)

@app.post("/audio-podcast", response_model=AudioPodcastResponse)
async def generate_audio_podcast(request: AudioPodcastRequest):
    """Generate audio podcast from document content"""
    
    try:
        print(f"Generating audio podcast for document '{request.document_name}' in notebook {request.notebook_id}")
        
        # Get chunks for this document
        document_chunks = [doc for doc in document_store 
                          if doc["notebook_id"] == request.notebook_id 
                          and doc["document_name"] == request.document_name]
        
        if not document_chunks:
            raise HTTPException(
                status_code=404, 
                detail=f"No content found for document '{request.document_name}'. Please make sure the document is uploaded and processed."
            )
        
        print(f"Found {len(document_chunks)} chunks for document '{request.document_name}'")
        
        # Combine chunks into full content
        full_content = "\n".join([chunk["chunk"] for chunk in document_chunks[:30]])  # Limit to first 30 chunks for longer audio
        
        # Generate podcast script using Groq
        podcast_prompt = f"""Create an engaging audio podcast script from the following document content. 
The script should be written for a narrator and structured for audio presentation.

IMPORTANT INSTRUCTIONS:
- Write in a conversational, engaging narrator style
- Include clear section headers/subheadings (mark them with "## " prefix)
- Make it sound natural when read aloud
- Add smooth transitions between sections
- Keep it informative but entertaining
- Length: Aim for 5-8 minutes of content (approximately 750-1200 words)
- Use storytelling techniques to keep listeners engaged

Document Content:
{full_content[:6000]}

Create a podcast script with:
1. A captivating introduction that hooks the listener
2. Main content organized into 3-4 clear sections with subheadings
3. A memorable conclusion that summarizes key takeaways

Write the complete script below:"""

        print("Generating podcast script with Groq...")
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert podcast scriptwriter who creates engaging, conversational audio content. Write scripts that sound natural when read aloud."
                },
                {
                    "role": "user",
                    "content": podcast_prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        podcast_script = completion.choices[0].message.content.strip()
        print(f"Generated script ({len(podcast_script)} characters)")
        
        # Clean the script for TTS (remove markdown headers for audio)
        tts_script = podcast_script.replace("## ", "").replace("#", "")
        
        # Generate audio using Edge TTS
        print("Generating audio with Edge TTS...")
        
        audio_filename = f"podcast_{request.notebook_id}_{uuid.uuid4().hex[:8]}.mp3"
        audio_dir = Path("data/generated_images")
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / audio_filename
        
        # Use Edge TTS with Jenny Neural voice (natural, professional)
        tts = edge_tts.Communicate(tts_script, voice="en-US-JennyNeural")
        
        # Run in thread to avoid event loop conflicts
        def run_edge_tts():
            import asyncio
            if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(tts.save(str(audio_path)))
        
        thread = threading.Thread(target=run_edge_tts)
        thread.start()
        thread.join()
        
        audio_url = f"http://localhost:8001/images/{audio_filename}"
        print(f"✅ Audio podcast saved: {audio_path}")
        
        # Calculate audio duration
        duration_seconds = 0
        duration_str = "0:00"
        try:
            from mutagen.mp3 import MP3
            audio_file = MP3(str(audio_path))
            duration_seconds = int(audio_file.info.length)
            duration_minutes = duration_seconds // 60
            duration_secs = duration_seconds % 60
            duration_str = f"{duration_minutes}:{duration_secs:02d}"
            print(f"Audio duration: {duration_str} ({duration_seconds} seconds)")
        except Exception as e:
            print(f"Could not calculate duration: {e}")
            # Keep defaults
        
        # Add to chat history
        notebook = next((nb for nb in notebooks_storage if nb["id"] == request.notebook_id), None)
        if notebook:
            if "chat_history" not in notebook:
                notebook["chat_history"] = []
            
            # Add user message
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-u",
                "role": "user",
                "content": f"🎙️ Audio Podcast: {request.document_name}",
                "timestamp": datetime.now().isoformat()
            })
            
            # Add bot response with audio player
            podcast_html = f"""
            <div style='border: 1px solid #a855f7; border-radius: 8px; padding: 10px; background: linear-gradient(135deg, rgba(168, 85, 247, 0.05) 0%, rgba(236, 72, 153, 0.02) 100%); margin: 10px 0; max-width: 550px;'>
                <div style='display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px;'>
                    <div style='display: flex; align-items: center; gap: 6px;'>
                        <span style='font-weight: 600; background: linear-gradient(135deg, #a855f7 0%, #ec4899 50%, #8b5cf6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 13px;'>
                            Audio Podcast
                        </span>
                        <span style='color: #9ca3af; font-size: 11px; font-weight: 600; padding: 2px 6px; background: rgba(168, 85, 247, 0.1); border-radius: 4px;'>
                            {duration_str}
                        </span>
                    </div>
                    <a href='{audio_url}' download='podcast.mp3' style='display: flex; align-items: center; gap: 4px; padding: 5px 10px; background: rgba(168, 85, 247, 0.2); border-radius: 5px; cursor: pointer; text-decoration: none; transition: all 0.2s; color: #a855f7; font-size: 11px; font-weight: 500;' onmouseover='this.style.background="rgba(168, 85, 247, 0.4)"' onmouseout='this.style.background="rgba(168, 85, 247, 0.2)"' title='Download Audio'>
                        <svg width='12' height='12' viewBox='0 0 16 16' fill='#a855f7'>
                            <path d='M8.5 1.5A.5.5 0 0 1 9 2v5.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 1 1 .708-.708L7.5 7.793V2A.5.5 0 0 1 8 1.5z'/>
                            <path d='M3 14.5a.5.5 0 0 1-.5-.5V11a.5.5 0 0 1 1 0v3h9v-3a.5.5 0 0 1 1 0v3a.5.5 0 0 1-.5.5h-10z'/>
                        </svg>
                        Download
                    </a>
                </div>
                <div style='background: rgba(0, 0, 0, 0.3); border-radius: 6px; padding: 6px;'>
                    <audio id='podcast-audio-{request.notebook_id}' controls controlsList='nodownload' style='width: 100%; height: 30px; outline: none;'>
                        <source src='{audio_url}' type='audio/mpeg'>
                        Your browser does not support the audio element.
                    </audio>
                </div>
                <details style='margin-top: 8px;'>
                    <summary style='cursor: pointer; color: #a855f7; font-weight: 500; padding: 5px 8px; background: rgba(168, 85, 247, 0.06); border-radius: 4px; font-size: 11px; user-select: none;'>
                        Script & Navigation
                    </summary>
                    <div id='script-container-{request.notebook_id}' style='margin-top: 8px; padding: 10px; background: rgba(0, 0, 0, 0.2); border-radius: 6px; font-size: 11px; line-height: 1.5; color: #e5e7eb; max-height: 250px; overflow-y: auto;'>
                        <div style='margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(168, 85, 247, 0.3);'>
                            <p style='color: #9ca3af; font-size: 10px; margin: 0 0 4px 0;'>Click any timestamp to jump to that section:</p>
                        </div>
{_format_script_with_timestamps(podcast_script, duration_seconds or 0)}
                    </div>
                </details>
            </div>
            <script>
            (function() {{
                const audio = document.getElementById('podcast-audio-{request.notebook_id}');
                const scriptContainer = document.getElementById('script-container-{request.notebook_id}');
                
                // Update duration display when audio metadata loads
                audio.addEventListener('loadedmetadata', function() {{
                    const duration = Math.floor(audio.duration);
                    const minutes = Math.floor(duration / 60);
                    const seconds = duration % 60;
                    const durationStr = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
                    
                    // Update the duration badge if it shows 0:00
                    const durationBadges = document.querySelectorAll('[style*="background: rgba(168, 85, 247, 0.1)"]');
                    for (let badge of durationBadges) {{
                        if (badge.textContent.trim() === '0:00') {{
                            badge.textContent = durationStr;
                        }}
                    }}
                }});
                
                if (scriptContainer) {{
                    scriptContainer.addEventListener('click', function(e) {{
                        if (e.target.classList.contains('timestamp-link')) {{
                            const seconds = parseFloat(e.target.dataset.seconds);
                            if (audio && !isNaN(seconds)) {{
                                audio.currentTime = seconds;
                                audio.play();
                                e.target.style.background = 'linear-gradient(135deg, #a855f7 0%, #ec4899 100%)';
                                setTimeout(() => {{
                                    e.target.style.background = 'rgba(168, 85, 247, 0.2)';
                                }}, 500);
                            }}
                        }}
                    }});
                }}
            }})();
            </script>
            """
            
            notebook["chat_history"].append({
                "id": f"{len(notebook['chat_history']) + 1}-a",
                "role": "assistant",
                "content": podcast_html,
                "timestamp": datetime.now().isoformat()
            })
            
            save_notebooks()
        
        return AudioPodcastResponse(
            success=True,
            audio_url=audio_url,
            script=podcast_script,
            message=f"Audio podcast generated successfully for {request.document_name}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating audio podcast: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating audio podcast: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
