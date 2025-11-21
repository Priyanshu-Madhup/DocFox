# DocFox 🦊

> AI-Powered Document Intelligence Platform - NotebookLM-style interface with advanced features

DocFox is a full-stack AI document assistant that combines document processing, AI chat, audio podcasts, visual presentations, and more - all in a clean, minimal interface inspired by NotebookLM.

## ✨ Features

### 📚 Document Management
- **Upload & Process PDFs** - Extract text and create searchable embeddings
- **Multiple Notebooks** - Organize documents by project/topic
- **Smart Chunking** - Intelligent document segmentation for better AI responses
- **Vector Search** - Fast semantic search using FAISS + Sentence Transformers

### 🤖 AI Assistant (Groq LLaMA 3.3-70B)
- **Context-Aware Chat** - RAG-powered responses using your documents
- **Chat History** - Persistent conversation tracking
- **Streaming Responses** - Real-time AI output
- **Smart Context** - Automatically retrieves relevant document chunks

### 🎙️ Audio Podcast Generation
- **AI Narration** - Generates 5-8 minute audio podcasts from documents
- **Natural Voice** - Edge TTS with Jenny Neural voice
- **Script Generation** - Creates engaging podcast scripts with timestamps
- **Download & Navigate** - Clickable timestamps and MP3 download

### 🎬 Visual Podcast (Slides)
- **Auto-Generate Slides** - Creates presentation slides from documents
- **Custom Templates** - Professional slide designs with text overlay
- **Bullet Points** - Key takeaways extracted by AI
- **Export Ready** - High-quality PNG slides

### 🌐 Web & Content Features
- **Web Scraping** - Extract content from URLs (Firecrawl)
- **YouTube Video Search** - Find relevant videos by topic (Serper API)
- **Mindmap Generation** - Visual knowledge graphs
- **Website Generation** - Create HTML sites from documents

### 📝 Editor & UI
- **Markdown Editor** - Rich text editing with auto-save
- **Dark/Light Mode** - Theme toggle with system preference
- **Responsive Design** - Mobile-friendly interface
- **LocalStorage Persistence** - Auto-save your work

## 🚀 Getting Started

### Prerequisites

- **Node.js** 16+ (for frontend)
- **Python** 3.8+ (for backend)
- **API Keys** (see Configuration below)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/docfox.git
cd docfox
```

2. **Install frontend dependencies**
```bash
npm install
```

3. **Install backend dependencies**
```bash
cd backend
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cd backend
cp .env.example .env
# Edit .env with your API keys
```

### Configuration

Create a `backend/.env` file with the following API keys:

```env
# Required API Keys
GROQ_API_KEY=your-groq-api-key-here          # Get from: https://console.groq.com
FIRECRAWL_API_KEY=your-firecrawl-api-key    # Get from: https://firecrawl.dev
SERPER_API_KEY=your-serper-api-key          # Get from: https://serper.dev

# Application Settings
SECRET_KEY=your-random-secret-key-here
DATABASE_URL=sqlite:///./docfox.db
```

### Running the Application

**Start Backend (Terminal 1):**
```bash
cd backend
python main.py
# Backend runs on http://localhost:8001
```

**Start Frontend (Terminal 2):**
```bash
npm start
# Frontend runs on http://localhost:3000
```

The app should open automatically in your browser at `http://localhost:3000`.

## 📁 Project Structure

```
docfox/
├── backend/
│   ├── main.py              # FastAPI backend
│   ├── auth.py              # Authentication
│   ├── database.py          # SQLite database
│   ├── models.py            # Data models
│   ├── schemas.py           # Pydantic schemas
│   ├── flashcard_system.py  # Flashcard generation
│   ├── quiz_system.py       # Quiz generation
│   ├── routers/             # API route modules
│   ├── data/                # Document storage
│   │   ├── notebooks.json
│   │   ├── processed_documents.json
│   │   └── uploaded_files/
│   └── requirements.txt
│
├── src/
│   ├── components/          # React components
│   │   ├── Sidebar.js       # Notebook list
│   │   ├── PageList.js      # Document list + AI Studio
│   │   ├── NoteEditor.js    # Markdown editor
│   │   ├── AIPanel.js       # Chat interface
│   │   ├── TopBar.js        # Navigation
│   │   └── (modals for various features)
│   ├── context/
│   │   └── AuthContext.js   # Authentication context
│   └── state/
│       └── notebookState.js # State management
│
├── public/
│   └── ppt_temp.png        # Slide template
└── README.md
```

## 🛠️ Tech Stack

### Frontend
- **React** 18 - UI framework
- **React Router** - Navigation
- **LocalStorage** - Client-side persistence
- **CSS3** - Styling with gradients & animations

### Backend
- **FastAPI** - Python web framework
- **Groq API** - LLaMA 3.3-70B language model
- **Sentence Transformers** - Document embeddings
- **FAISS** - Vector similarity search
- **PyPDF2** - PDF text extraction
- **Edge TTS** - Audio generation
- **Pillow (PIL)** - Image processing
- **MoviePy** - Video generation
- **Firecrawl** - Web scraping
- **Serper API** - Video search

### Storage
- **SQLite** - User data
- **JSON Files** - Document metadata
- **LocalStorage** - Frontend state

## 🎯 Key Features Explained

### Audio Podcast
1. Retrieves 30 document chunks for context
2. Generates 5-8 minute podcast script using LLaMA 3.3-70B
3. Converts script to speech with Edge TTS (Jenny Neural voice)
4. Creates clickable timestamp navigation
5. Provides MP3 download

### Visual Podcast
1. Extracts key information from document
2. Generates 5-6 slide outlines with bullet points
3. Overlays text on professional slide template
4. Exports high-quality PNG slides

### RAG Chat
1. User sends a question
2. Embeds question using Sentence Transformers
3. Searches FAISS index for top 10 relevant chunks
4. Sends chunks + question to LLaMA 3.3-70B
5. Streams AI response back to user

## 🔒 Security Notes

- ✅ `.env` files are gitignored
- ✅ API keys stored in environment variables
- ✅ No hardcoded credentials
- ⚠️ Always use `.env.example` as template
- ⚠️ Never commit your actual `.env` file

## 🐛 Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (need 3.8+)
- Install dependencies: `pip install -r requirements.txt`
- Verify API keys in `.env`

**Frontend won't connect:**
- Ensure backend is running on port 8001
- Check CORS settings in `main.py`
- Clear browser cache

**Audio generation fails:**
- Verify Edge TTS is installed: `pip install edge-tts`
- Check disk space in `data/generated_images/`

**No search results:**
- Upload and process a PDF first
- Wait for embedding generation to complete
- Check console for FAISS index errors

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- Built with [Create React App](https://create-react-app.dev/)
- Inspired by [NotebookLM](https://notebooklm.google/)
- AI powered by [Groq](https://groq.com/)
- Voice synthesis by [Edge TTS](https://github.com/rany2/edge-tts)

---

Made with ❤️ using React, FastAPI, and LLaMA 3.3-70B
