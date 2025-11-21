import React, { useEffect, useState } from 'react';
import './App.css';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import PageList from './components/PageList';
import NoteEditor from './components/NoteEditor';
import MindmapModal from './components/MindmapModal';
import VideosModal from './components/VideosModal';
import VisualPodcastModal from './components/VisualPodcastModal';
import WebsiteModal from './components/WebsiteModal';
import NewNotebookModal from './components/NewNotebookModal';
import QuizModal from './components/QuizModal';
import FlashcardModal from './components/FlashcardModal';
import { useNotebooks } from './state/notebookState';

function App() {
  const [darkMode] = useState(() => window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);
  const [mindmapOpen, setMindmapOpen] = useState(false);
  const [mindmapNotebookId, setMindmapNotebookId] = useState(null);
  const [mindmapDocumentName, setMindmapDocumentName] = useState(null);
  const [videosOpen, setVideosOpen] = useState(false);
  const [videosNotebookId, setVideosNotebookId] = useState(null);
  const [videosDocumentName, setVideosDocumentName] = useState(null);
  const [visualPodcastOpen, setVisualPodcastOpen] = useState(false);
  const [visualPodcastNotebookId, setVisualPodcastNotebookId] = useState(null);
  const [visualPodcastDocumentName, setVisualPodcastDocumentName] = useState(null);
  const [visualPodcastLoading, setVisualPodcastLoading] = useState(false);
  const [websiteModalOpen, setWebsiteModalOpen] = useState(false);
  const [newNotebookModalOpen, setNewNotebookModalOpen] = useState(false);
  const [quizOpen, setQuizOpen] = useState(false);
  const [quizNotebookId, setQuizNotebookId] = useState(null);
  const [flashcardOpen, setFlashcardOpen] = useState(false);
  const [flashcardNotebookId, setFlashcardNotebookId] = useState(null);

  const {
    notebooks,
    currentNotebook,
    currentNotebookId,
    setCurrentNotebookId,
    setNotebookTitle,
    renameNotebook,
    addNotebook,
    deleteNotebook,
    addPage,
    currentPageId,
    setCurrentPageId,
    deletePage
    ,
    refreshNotebook
  } = useNotebooks();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  const handleMindmapClick = (notebookId, documentName) => {
    console.log('handleMindmapClick called with:', { notebookId, documentName });
    console.log('Current state:', { mindmapOpen, mindmapNotebookId, mindmapDocumentName });
    
    if (!notebookId || !documentName) {
      console.error('Missing required parameters for mindmap');
      return;
    }
    
    setMindmapOpen(true);
    setMindmapNotebookId(notebookId);
    setMindmapDocumentName(documentName);
    
    console.log('State should be updated to:', { 
      mindmapOpen: true, 
      mindmapNotebookId: notebookId, 
      mindmapDocumentName: documentName 
    });
  };

  const handleVideosClick = (notebookId, documentName) => {
    console.log('handleVideosClick called with:', { notebookId, documentName });
    console.log('Current state:', { videosOpen, videosNotebookId, videosDocumentName });
    
    if (!notebookId || !documentName) {
      console.error('Missing required parameters for videos');
      return;
    }
    
    setVideosOpen(true);
    setVideosNotebookId(notebookId);
    setVideosDocumentName(documentName);
    
    console.log('Videos state should be updated to:', { 
      videosOpen: true, 
      videosNotebookId: notebookId, 
      videosDocumentName: documentName 
    });
  };

  const handleVisualPodcastClick = (notebookId, documentName) => {
    console.log('handleVisualPodcastClick called with:', { notebookId, documentName });
    console.log('Current state:', { visualPodcastOpen, visualPodcastNotebookId, visualPodcastDocumentName });
    
    if (!notebookId || !documentName) {
      console.error('Missing required parameters for visual podcast');
      return;
    }
    
    setVisualPodcastOpen(true);
    setVisualPodcastNotebookId(notebookId);
    setVisualPodcastDocumentName(documentName);
    
    console.log('Visual Podcast state should be updated to:', { 
      visualPodcastOpen: true, 
      visualPodcastNotebookId: notebookId, 
      visualPodcastDocumentName: documentName 
    });
  };

  const handleCreateWebsiteNotebook = async (websiteData) => {
    try {
      // The backend already created the notebook, so we need to refresh the notebooks
      // and set the current notebook to the newly created one
      setCurrentNotebookId(websiteData.notebook_id);
      
      // For now, we'll need to refresh or manually add the notebook
      // This should trigger a refresh of the notebooks list
      window.location.reload(); // Temporary solution - ideally we'd update the state
    } catch (error) {
      console.error('Error handling website notebook creation:', error);
    }
  };

  const handleAddNotebook = () => {
    setNewNotebookModalOpen(true);
  };

  const handleCreateNotebook = async (notebookName) => {
    await addNotebook(notebookName);
  };

  const handleVisualPodcastClickFromChat = (notebookId, documentName, savedData) => {
    console.log('Opening saved visual podcast:', { notebookId, documentName, savedData });
    
    if (!notebookId || !documentName || !savedData) {
      console.error('Missing required parameters for visual podcast');
      return;
    }
    
    // Set the modal state to open with saved data
    setVisualPodcastOpen(true);
    setVisualPodcastNotebookId(notebookId);
    setVisualPodcastDocumentName(documentName);
    
    // Store the saved data for the modal to use
    window.savedVisualPodcastData = savedData;
    
    console.log('Visual Podcast state should be updated to:', { 
      visualPodcastOpen: true, 
      visualPodcastNotebookId: notebookId, 
      visualPodcastDocumentName: documentName,
      savedData 
    });
  };

  const handleQuizClick = (notebookId) => {
    console.log('handleQuizClick called with:', { notebookId });
    
    if (!notebookId) {
      console.error('Missing required notebook ID for quiz');
      return;
    }
    
    setQuizOpen(true);
    setQuizNotebookId(notebookId);
  };

  const handleFlashcardClick = (notebookId) => {
    console.log('handleFlashcardClick called with:', { notebookId });
    
    if (!notebookId) {
      console.error('Missing required notebook ID for flashcards');
      return;
    }
    
    setFlashcardOpen(true);
    setFlashcardNotebookId(notebookId);
  };

  return (
    <div className="app">
      <Navbar />
      <div className="layoutRoot">
        {sidebarOpen && (
          <Sidebar
            notebooks={notebooks}
            currentNotebookId={currentNotebookId}
            onSelectNotebook={setCurrentNotebookId}
            onAddNotebook={handleAddNotebook}
            onDeleteNotebook={deleteNotebook}
            onRenameNotebook={renameNotebook}
            onToggleSidebar={() => setSidebarOpen(s => !s)}
            onOpenWebsiteModal={() => setWebsiteModalOpen(true)}
          />
        )}
        <div className="mainColumn">
          <div className="workspaceRow">
            <div className="editorColumn">
              <NoteEditor 
                notebook={currentNotebook} 
                onUpdateNotebook={setNotebookTitle}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={() => setSidebarOpen(s => !s)}
                rightSidebarOpen={rightSidebarOpen}
                onToggleRightSidebar={() => setRightSidebarOpen(s => !s)}
                onRenameNotebook={(id, title) => setNotebookTitle(id, title)}
                onVisualPodcastClick={handleVisualPodcastClickFromChat}
              />
            </div>
          </div>
        </div>
        {rightSidebarOpen && (
          <PageList
            pages={currentNotebook?.pages || []}
            currentPageId={currentPageId}
            onSelectPage={setCurrentPageId}
            onDeletePage={deletePage}
            onUploadPDF={addPage}
            onRefreshNotebook={refreshNotebook}
            onToggleRightSidebar={() => setRightSidebarOpen(s => !s)}
            currentNotebook={currentNotebook}
            onMindmapClick={handleMindmapClick}
            onVideosClick={handleVideosClick}
            onVisualPodcastClick={handleVisualPodcastClick}
            onVisualPodcastLoadingChange={setVisualPodcastLoading}
            onQuizClick={handleQuizClick}
            onFlashcardClick={handleFlashcardClick}
          />
        )}
      </div>
      
      <MindmapModal 
        isOpen={mindmapOpen}
        onClose={() => {
          setMindmapOpen(false);
          setMindmapDocumentName(null);
        }}
        notebookId={mindmapNotebookId}
        documentName={mindmapDocumentName}
      />
      
      <VideosModal 
        isOpen={videosOpen}
        onClose={() => {
          setVideosOpen(false);
          setVideosDocumentName(null);
        }}
        notebookId={videosNotebookId}
        documentName={videosDocumentName}
      />
      
      <VisualPodcastModal 
        isOpen={visualPodcastOpen}
        onClose={() => {
          setVisualPodcastOpen(false);
          setVisualPodcastDocumentName(null);
          setVisualPodcastLoading(false); // Stop loading when modal closes
        }}
        notebookId={visualPodcastNotebookId}
        documentName={visualPodcastDocumentName}
        onLoadingChange={setVisualPodcastLoading}
      />
      
      <WebsiteModal 
        isOpen={websiteModalOpen}
        onClose={() => setWebsiteModalOpen(false)}
        onCreateNotebook={handleCreateWebsiteNotebook}
      />
      
      <NewNotebookModal 
        isOpen={newNotebookModalOpen}
        onClose={() => setNewNotebookModalOpen(false)}
        onConfirm={handleCreateNotebook}
      />
      
      <QuizModal 
        isOpen={quizOpen}
        onClose={() => {
          setQuizOpen(false);
          setQuizNotebookId(null);
        }}
        notebookId={quizNotebookId}
      />
      
      <FlashcardModal 
        isOpen={flashcardOpen}
        onClose={() => {
          setFlashcardOpen(false);
          setFlashcardNotebookId(null);
        }}
        notebookId={flashcardNotebookId}
      />
    </div>
  );
}

export default App;
