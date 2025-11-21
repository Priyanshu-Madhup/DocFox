import React, { useState, useRef, useEffect } from 'react';
import './NoteEditor.css';

export default function NoteEditor({ notebook, onUpdateNotebook, sidebarOpen, onToggleSidebar, rightSidebarOpen, onToggleRightSidebar, onRenameNotebook, onVisualPodcastClick }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState('en');
  const [working, setWorking] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const titleInputRef = useRef(null);

  // Language options
  const languages = [
    { code: 'en', name: 'English', flag: '🇺🇸' },
    { code: 'es', name: 'Spanish', flag: '🇪🇸' },
    { code: 'fr', name: 'French', flag: '🇫🇷' },
    { code: 'de', name: 'German', flag: '🇩🇪' },
    { code: 'it', name: 'Italian', flag: '🇮🇹' },
    { code: 'pt', name: 'Portuguese', flag: '🇵🇹' },
    { code: 'ru', name: 'Russian', flag: '🇷🇺' },
    { code: 'zh', name: 'Chinese', flag: '🇨🇳' },
    { code: 'ja', name: 'Japanese', flag: '🇯🇵' },
    { code: 'ko', name: 'Korean', flag: '🇰🇷' },
    { code: 'ar', name: 'Arabic', flag: '🇸🇦' },
    { code: 'hi', name: 'Hindi', flag: '🇮🇳' },
  ];

  // Load chat history when notebook changes
  useEffect(() => {
    if (!notebook) {
      setMessages([]);
      setTitleValue('');
      return;
    }

    setTitleValue(notebook.title || '');

    // Load chat history from backend
    const loadChatHistory = async () => {
      try {
        const response = await fetch(`http://localhost:8001/notebooks/${notebook.id}/chat`);
        if (response.ok) {
          const data = await response.json();
          setMessages(data.chat_history || []);
        } else {
          // Use local chat history if backend not available
          setMessages(notebook.chat_history || []);
        }
      } catch (error) {
        console.error('Error loading chat history:', error);
        // Use local chat history if backend not available
        setMessages(notebook.chat_history || []);
      }
    };

    loadChatHistory();
    
    // Set up global refresh function for other components to call
    window.refreshChatHistory = loadChatHistory;
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebook?.id]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, working]);

  // Focus input when notebook changes or component mounts
  useEffect(() => {
    if (notebook && inputRef.current) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebook?.id]);

  if (!notebook) return <div className="NoteEditor__empty">Select a notebook to start chatting with the assistant.</div>;

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = { id: Date.now() + '-u', role: 'user', content: input.trim() };
    setMessages(m => [...m, userMsg]);
    const prompt = input.trim();
    setInput('');
    setWorking(true);
    
    try {
      const response = await fetch('http://localhost:8001/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: prompt,
          notebook_id: notebook.id,
          language: selectedLanguage
        }),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      const aiMsg = { 
        id: Date.now() + '-a', 
        role: 'assistant', 
        content: data.response
      };
      setMessages(m => [...m, aiMsg]);
      
      // The backend now stores the chat history, so it will be available when we reload
    } catch (error) {
      console.error('Error calling chat API:', error);
      const errorMsg = { 
        id: Date.now() + '-a', 
        role: 'assistant', 
        content: `Sorry, I encountered an error: ${error.message}`
      };
      setMessages(m => [...m, errorMsg]);
    } finally {
      setWorking(false);
      // Focus back to input after sending message
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleTitleEdit = () => {
    setEditingTitle(true);
    setTimeout(() => {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }, 0);
  };

  const handleTitleSave = () => {
    if (titleValue.trim() && notebook && onRenameNotebook) {
      onRenameNotebook(notebook.id, titleValue.trim());
    }
    setEditingTitle(false);
  };

  const handleTitleCancel = () => {
    setTitleValue(notebook?.title || '');
    setEditingTitle(false);
  };

  const handleTitleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleTitleSave();
    } else if (e.key === 'Escape') {
      handleTitleCancel();
    }
  };

  const downloadChatAsPDF = async () => {
    if (!notebook || messages.length === 0) {
      alert('No chat history to download');
      return;
    }

    try {
      // Prepare chat data for PDF generation
      const chatData = {
        notebook_id: notebook.id,
        notebook_title: notebook.title,
        messages: messages,
        generated_at: new Date().toISOString()
      };

      // Call backend PDF generation endpoint
      const response = await fetch('http://localhost:8001/generate-chat-pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(chatData),
      });

      if (response.ok) {
        // Get the PDF blob
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `${notebook.title}_chat_export.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        alert('Failed to generate PDF');
      }
    } catch (error) {
      console.error('Error downloading PDF:', error);
      alert('Error downloading PDF: ' + error.message);
    }
  };

  return (
    <div className="NoteEditor">
      <div className="NoteEditor__chat">
        <div className="NoteEditor__header">
          <div className="NoteEditor__headerLeft">
            {!sidebarOpen && (
              <button 
                onClick={onToggleSidebar} 
                className="NoteEditor__hamburger"
                title="Show sidebar"
                aria-label="Show sidebar"
              >
                <i className="bi bi-layout-sidebar-inset"></i>
              </button>
            )}
            {editingTitle ? (
              <input
                ref={titleInputRef}
                type="text"
                value={titleValue}
                onChange={(e) => setTitleValue(e.target.value)}
                onKeyDown={handleTitleKeyPress}
                onBlur={handleTitleSave}
                className="NoteEditor__titleInput"
                placeholder="Notebook title..."
              />
            ) : (
              <h3 
                className="NoteEditor__title" 
                onClick={handleTitleEdit}
                title="Click to edit title"
              >
                {notebook?.title || 'Chat'}
              </h3>
            )}
          </div>
          <div className="NoteEditor__headerRight">
            <button 
              onClick={downloadChatAsPDF}
              className="NoteEditor__downloadBtn"
              title="Download chat as PDF"
              disabled={!notebook || messages.length === 0}
            >
              <i className="bi bi-download"></i>
              <span>Download PDF</span>
            </button>
            {!rightSidebarOpen && (
              <button 
                onClick={onToggleRightSidebar} 
                className="NoteEditor__hamburger"
                title="Show right sidebar"
                aria-label="Show right sidebar"
              >
                <i className="bi bi-layout-sidebar-inset-reverse"></i>
              </button>
            )}
          </div>
        </div>
        <div className="NoteEditor__messages">
          {messages.length === 0 && (
            <div className="NoteEditor__welcome">
              <h1 className="welcome-greeting">Good Evening</h1>
              <p className="welcome-subtitle">What would you like to do?</p>
              <div className="welcome-features-grid">
                <div className="welcome-feature-card">
                  <i className="bi bi-mic-fill feature-icon"></i>
                  <h4>Audio Podcast</h4>
                  <p>Generate natural narration from your documents</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-camera-reels-fill feature-icon"></i>
                  <h4>Visual Podcast</h4>
                  <p>Create video presentations with slides and audio</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-diagram-3-fill feature-icon"></i>
                  <h4>Mind Maps</h4>
                  <p>Visualize concepts and relationships interactively</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-play-btn-fill feature-icon"></i>
                  <h4>Video Summaries</h4>
                  <p>Get YouTube-style video explanations</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-chat-dots-fill feature-icon"></i>
                  <h4>AI Chat</h4>
                  <p>Ask questions about your documents naturally</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-card-list feature-icon"></i>
                  <h4>Flashcards</h4>
                  <p>Study with AI-generated flashcards</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-patch-question-fill feature-icon"></i>
                  <h4>Quiz Mode</h4>
                  <p>Test your knowledge with AI quizzes</p>
                </div>
                <div className="welcome-feature-card">
                  <i className="bi bi-globe2 feature-icon"></i>
                  <h4>Website Analysis</h4>
                  <p>Analyze and chat with web content</p>
                </div>
              </div>
            </div>
          )}
          {messages.map(msg => (
            <div key={msg.id} className={`message message--${msg.role}`}>
              {msg.type === 'visual_podcast' ? (
                // Special rendering for visual podcast messages
                <div className="message__content message__visual-podcast">
                  <div className="visual-podcast-preview">
                    <div className="visual-podcast-header">
                      <i className="bi bi-camera-reels"></i>
                      <span className="visual-podcast-title">{msg.message}</span>
                      <span className="visual-podcast-meta">({msg.total_slides} slides)</span>
                    </div>
                    <button 
                      className="visual-podcast-play-btn"
                      onClick={() => {
                        // Open the visual podcast modal with saved data
                        if (typeof onVisualPodcastClick === 'function') {
                          onVisualPodcastClick(notebook.id, msg.document_name, msg);
                        }
                      }}
                    >
                      <i className="bi bi-play-circle-fill"></i>
                      <span>Open Visual Podcast</span>
                    </button>
                    {msg.video_url && (
                      <div className="visual-podcast-video-info">
                        <i className="bi bi-camera-video"></i>
                        <span>Video available</span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                // Normal message rendering
                <div 
                  className="message__content" 
                  dangerouslySetInnerHTML={{ __html: msg.content || msg.message }}
                ></div>
              )}
            </div>
          ))}
          {working && (
            <div className="message message--assistant">
              <div className="message__content">Thinking...</div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        
        <div className="NoteEditor__inputArea">
          <div className="NoteEditor__inputContainer">
            <textarea
              ref={inputRef}
              className="NoteEditor__input"
              placeholder="Ask about your notebook or request analysis..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              disabled={working}
              rows={1}
            />
            <div className="NoteEditor__inputControls">
              <select 
                className="NoteEditor__languageSelect"
                value={selectedLanguage}
                onChange={e => setSelectedLanguage(e.target.value)}
                disabled={working}
                title="Select response language"
              >
                {languages.map(lang => (
                  <option key={lang.code} value={lang.code}>
                    {lang.flag} {lang.name}
                  </option>
                ))}
              </select>
              <button 
                onClick={sendMessage} 
                disabled={!input.trim() || working}
                className="NoteEditor__sendBtn"
                title="Send message"
              >
                <i className="bi bi-send-fill"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
