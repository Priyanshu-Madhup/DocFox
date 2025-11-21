import React, { useRef, useState, useEffect } from 'react';
import './PageList.css';

export default function PageList({ pages, currentPageId, onSelectPage, onDeletePage, onUploadPDF, onToggleRightSidebar, currentNotebook, onMindmapClick, onVideosClick, onVisualPodcastClick, onVisualPodcastLoadingChange, onRefreshNotebook, onQuizClick, onFlashcardClick }) {
  const fileInputRef = useRef(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [selectedPages, setSelectedPages] = useState(new Set());
  const [processedPages, setProcessedPages] = useState(new Set()); // Track processed PDFs
  const [miniWindowOpenFor, setMiniWindowOpenFor] = useState(null); // Track which page has mini window open
  const [webSearchLoading, setWebSearchLoading] = useState(false); // Track web search loading state
  const [visualPodcastLoading, setVisualPodcastLoading] = useState(false); // Track visual podcast loading state
  const [audioPodcastLoading, setAudioPodcastLoading] = useState(false); // Track audio podcast loading state

  console.log('PageList props received:', { onMindmapClick: !!onMindmapClick });

  // Helper function to determine if a page is processed
  const isPageProcessed = (page) => {
    // Always check backend state first if available
    if (processedPages.has(page.id)) {
      return true;
    }
    
    // If loading or no backend confirmation yet, check page metadata for PDF processing indicators
    if (page.type === 'pdf') {
      return !!(page.chunks_count || page.file_path || page.token_count);
    }
    
    return false;
  };

  // Load processed documents status when notebook changes
  useEffect(() => {
    const loadProcessedStatus = async () => {
      if (!currentNotebook?.id) {
        setProcessedPages(new Set()); // Clear processed pages
        return;
      }
      
      // Reset state when switching notebooks
      setProcessedPages(new Set()); // Clear previous notebook's processed pages
      
      try {
        const response = await fetch(`http://localhost:8001/notebooks/${currentNotebook.id}/processed-documents`);
        if (response.ok) {
          const data = await response.json();
          
          // Find pages that have been processed
          const processedFileNames = new Set(data.processed_documents.map(doc => doc.filename));
          const processedPageIds = new Set();
          
          pages.forEach(page => {
            if (page.type === 'pdf' && page.filename && processedFileNames.has(page.filename)) {
              processedPageIds.add(page.id);
            }
          });
          
          setProcessedPages(processedPageIds);
          console.log(`Loaded ${processedPageIds.size} processed documents for notebook ${currentNotebook.id}:`, Array.from(processedPageIds));
        }
      } catch (error) {
        console.error('Error loading processed documents status:', error);
      }
    };

    // Reset selection but load processed status
    setSelectedPages(new Set());
    setMiniWindowOpenFor(null);
    loadProcessedStatus();
  }, [currentNotebook?.id, pages]); // Include pages to reload when pages change

  // Close mini window when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (miniWindowOpenFor && !event.target.closest('.action-mini-window') && !event.target.closest('.sourceItem__actions-main')) {
        setMiniWindowOpenFor(null);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [miniWindowOpenFor]);

  const handleFileUpload = (event) => {
    const files = Array.from(event.target.files);
    const pdfFiles = files.filter(file => file.type === 'application/pdf');
    
    if (pdfFiles.length > 0) {
      if (pdfFiles.length !== files.length) {
        alert(`${files.length - pdfFiles.length} non-PDF files were ignored. Only PDF files are supported.`);
      }
      onUploadPDF(pdfFiles); // Pass array of files instead of single file
      event.target.value = ''; // Reset input
    } else {
      alert('Please select at least one PDF file');
    }
  };

  const handlePageSelection = async (pageId) => {
    const page = pages.find(p => p.id === pageId);
    const isCurrentlyProcessed = isPageProcessed(page);
    const isCurrentlySelected = selectedPages.has(pageId);
    
    // If it's a processed PDF and we're unselecting it, remove from vector DB
    if (isCurrentlyProcessed && isCurrentlySelected && page?.type === 'pdf' && page?.file) {
      try {
        const response = await fetch('http://localhost:8001/remove-document', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            document_name: page.file.name,
            notebook_id: currentNotebook?.id || 1
          }),
        });
        
        if (response.ok) {
          const result = await response.json();
          console.log(`Removed ${result.chunks_removed} chunks for ${page.file.name}`);
          
          // Remove from processed pages
          setProcessedPages(prev => {
            const newSet = new Set(prev);
            newSet.delete(pageId);
            return newSet;
          });
        } else {
          console.error('Failed to remove document from vector database');
        }
      } catch (error) {
        console.error('Error removing document:', error);
      }
    }
    
    // Handle normal selection/deselection
    setSelectedPages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(pageId)) {
        newSet.delete(pageId);
      } else {
        newSet.add(pageId);
      }
      return newSet;
    });
  };

  const handleSelectAll = () => {
    if (selectedPages.size === pages.length) {
      setSelectedPages(new Set()); // Deselect all
    } else {
      setSelectedPages(new Set(pages.map(p => p.id))); // Select all
    }
  };

  const triggerFileUpload = () => {
    fileInputRef.current?.click();
  };

  const handleProcess = async () => {
    if (selectedPages.size === 0) {
      alert('Please select at least one PDF to process');
      return;
    }
    
    setIsProcessing(true);
    setProcessingProgress(0);
    
    try {
      // Get selected pages (PDFs only) that haven't been processed yet
      const selectedPDFs = pages.filter(p => 
        selectedPages.has(p.id) && 
        p.type === 'pdf' && 
        (p.file || p.filename) && // Accept either fresh uploads (with file) or persisted PDFs (with filename)
        !isPageProcessed(p) // Only process unprocessed PDFs
      );
      
      if (selectedPDFs.length === 0) {
        // Check if there are any PDFs selected but they're already processed
        const selectedPDFsIncludingProcessed = pages.filter(p => 
          selectedPages.has(p.id) && 
          p.type === 'pdf' && 
          (p.file || p.filename)
        );
        
        if (selectedPDFsIncludingProcessed.length > 0) {
          alert('Selected PDFs are already processed and ready for chat!');
        } else {
          alert('Please select valid PDF files to process');
        }
        setIsProcessing(false);
        return;
      }
      
      // Create FormData for file upload
      const formData = new FormData();
      const filesToUpload = [];
      const persistedFiles = [];
      
      selectedPDFs.forEach(pdf => {
        if (pdf.file) {
          // Fresh upload with file object
          formData.append('files', pdf.file);
          filesToUpload.push(pdf);
        } else if (pdf.filename) {
          // Persisted file - just send metadata
          persistedFiles.push({
            filename: pdf.filename,
            notebook_id: currentNotebook?.id || 1
          });
        }
      });
      
      formData.append('notebook_id', currentNotebook?.id || 1); // Use current notebook ID
      
      // If we have persisted files, send them separately
      if (persistedFiles.length > 0) {
        formData.append('persisted_files', JSON.stringify(persistedFiles));
      }
      
      setProcessingProgress(30);
      
      // Call the backend API
      const response = await fetch('http://localhost:8001/process-pdf', {
        method: 'POST',
        body: formData,
      });
      
      setProcessingProgress(70);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      await response.json(); // Process response but don't store unused result
      setProcessingProgress(100);

      // Refresh notebook pages from backend so processed PDFs are persisted and visible
      try {
        if (typeof onRefreshNotebook === 'function' && currentNotebook?.id) {
          await onRefreshNotebook(currentNotebook.id);
        }
      } catch (err) {
        console.error('Error refreshing notebook after processing:', err);
      }

      // Mark only newly processed PDFs as processed (keep them highlighted)
      const newlyProcessedIds = selectedPDFs.map(pdf => pdf.id);
      setProcessedPages(prev => new Set([...prev, ...newlyProcessedIds]));
      
      // Don't clear selection - keep processed PDFs highlighted
      
    } catch (error) {
      console.error('Error processing PDFs:', error);
      alert(`Error processing PDFs: ${error.message}`);
    } finally {
      setTimeout(() => {
        setIsProcessing(false);
        setProcessingProgress(0);
      }, 1000);
    }
  };

  return (
    <div className="PageList">
      <div className="PageList__header">
        <div className="PageList__headerTop">
          <h3>Sources</h3>
          <button 
            onClick={onToggleRightSidebar} 
            className="PageList__hamburger"
            title="Hide right sidebar"
            aria-label="Hide right sidebar"
          >
            <i className="bi bi-layout-sidebar-inset-reverse"></i>
          </button>
        </div>
        <div className="PageList__headerControls">
          <div className="PageList__leftControls">
            {pages.length > 0 && (
              <button 
                onClick={handleSelectAll}
                className="PageList__selectAllBtn"
              >
                {selectedPages.size === pages.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>
          <div className="PageList__rightControls">
            <button 
              onClick={handleProcess} 
              className="processBtn" 
              title={(() => {
                const unprocessedSelected = Array.from(selectedPages).filter(id => 
                  !processedPages.has(id) && pages.find(p => p.id === id)?.type === 'pdf'
                ).length;
                const processedSelected = Array.from(selectedPages).filter(id => 
                  processedPages.has(id)
                ).length;
                
                if (unprocessedSelected > 0) {
                  return `Process ${unprocessedSelected} new PDF${unprocessedSelected !== 1 ? 's' : ''}`;
                } else if (processedSelected > 0) {
                  return `${processedSelected} PDF${processedSelected !== 1 ? 's' : ''} already processed`;
                } else {
                  return 'Select PDFs to process';
                }
              })()}
              disabled={selectedPages.size === 0 || isProcessing}
            >
              {isProcessing ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" strokeDasharray="31.416" strokeDashoffset="31.416">
                    <animate attributeName="stroke-dasharray" dur="2s" values="0 31.416;15.708 15.708;0 31.416" repeatCount="indefinite"/>
                    <animate attributeName="stroke-dashoffset" dur="2s" values="0;-15.708;-31.416" repeatCount="indefinite"/>
                  </circle>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12,2A2,2 0 0,1 14,4C14,4.74 13.6,5.39 13,5.73V7H14A7,7 0 0,1 21,14H22A1,1 0 0,1 23,15V18A1,1 0 0,1 22,19H21V20A2,2 0 0,1 19,22H5A2,2 0 0,1 3,20V19H2A1,1 0 0,1 1,18V15A1,1 0 0,1 2,14H3A7,7 0 0,1 10,7H11V5.73C10.4,5.39 10,4.74 10,4A2,2 0 0,1 12,2M7.5,13A2.5,2.5 0 0,0 5,15.5A2.5,2.5 0 0,0 7.5,18A2.5,2.5 0 0,0 10,15.5A2.5,2.5 0 0,0 7.5,13M16.5,13A2.5,2.5 0 0,0 14,15.5A2.5,2.5 0 0,0 16.5,18A2.5,2.5 0 0,0 19,15.5A2.5,2.5 0 0,0 16.5,13Z" />
                </svg>
              )}
            </button>
            <button onClick={triggerFileUpload} className="uploadBtn" title="Upload PDFs (multiple files supported)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                <path d="M12,11L16,15H13V19H11V15H8L12,11Z" />
              </svg>
            </button>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={handleFileUpload}
          style={{ display: 'none' }}
        />
      </div>

      {isProcessing && (
        <div className="PageList__processing">
          <div className="processingBar">
            <div 
              className="processingBar__fill" 
              style={{ width: `${processingProgress}%` }}
            />
          </div>
          <span className="processingText">Processing {selectedPages.size} source{selectedPages.size !== 1 ? 's' : ''}... {processingProgress}%</span>
        </div>
      )}

      {webSearchLoading && (
        <div className="PageList__processing">
          <div className="webSearchLoader">
            <i className="bi bi-arrow-clockwise loading-spin"></i>
            <span>Searching the web for related information...</span>
          </div>
        </div>
      )}

      {visualPodcastLoading && (
        <div className="PageList__processing">
          <div className="webSearchLoader">
            <i className="bi bi-arrow-clockwise loading-spin"></i>
            <span>Generating AI-powered visual podcast...</span>
          </div>
        </div>
      )}

      {audioPodcastLoading && (
        <div className="PageList__processing">
          <div className="webSearchLoader">
            <i className="bi bi-mic-fill loading-spin"></i>
            <span>Generating audio podcast with AI narration...</span>
          </div>
        </div>
      )}

      <div className="PageList__content">
        {pages.map(p => {
          const isSelected = selectedPages.has(p.id);
          const isProcessed = isPageProcessed(p);
          const className = `sourceItem ${isSelected ? 'is-selected' : ''} ${isProcessed ? 'is-processed' : ''}`;
          
          return (
            <div key={p.id} className={className}>
              <button 
                onClick={() => handlePageSelection(p.id)} 
                className="sourceItem__main"
                title="Click to select for processing"
              >
                <div className="sourceItem__icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                  </svg>
                  {isProcessed && (
                    <div className="sourceItem__processedBadge">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M9,20.42L2.79,14.21L5.62,11.38L9,14.77L18.88,4.88L21.71,7.71L9,20.42Z" />
                      </svg>
                    </div>
                  )}
                </div>
                <div className="sourceItem__content">
                  <div className="sourceItem__title">{(p.title || 'Untitled').replace(/📄|📋|📃|🗎|🗋/g, '').trim()}</div>
                  <div className="sourceItem__meta">
                    {p.type === 'pdf' ? 'PDF Document' : 'Text Note'}
                    {isProcessed && <span className="processedIndicator"> • Processed</span>}
                  </div>
                </div>
              </button>
              
              {/* Action buttons container */}
              <div className="sourceItem__actions">
                {/* Main action button - only for processed PDFs */}
                {p.type === 'pdf' && isProcessed && (
                  <div className="action-mini-window-container">
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setMiniWindowOpenFor(miniWindowOpenFor === p.id ? null : p.id);
                      }} 
                      title={`Actions for ${p.filename || p.title}`} 
                      className="sourceItem__actions-main"
                    >
                      <i className="bi bi-hdd-stack"></i>
                    </button>
                  </div>
                )}
                
                {/* Delete button */}
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeletePage(p.id);
                  }} 
                  title="Remove source" 
                  className="sourceItem__delete"
                >
                  <i className="bi bi-trash"></i>
                </button>
              </div>
            </div>
          );
        })}
        
        {pages.length === 0 && (
          <div className="emptyState">
            <div className="emptyState__icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor" opacity="0.3">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
              </svg>
            </div>
            <div className="emptyState__content">
              <h4>No sources yet</h4>
              <p>Upload PDFs to start analyzing your documents</p>
            </div>
          </div>
        )}
      </div>

      {/* Mini Action Window */}
      {miniWindowOpenFor && (
        <div className="action-mini-window-overlay">
          <div className="action-mini-window">
            <div className="action-mini-window__header">
              <div className="action-mini-window__header-content">
                <h4>DocFox AI Studio</h4>
                <p>Choose your AI-powered tool</p>
              </div>
              <button 
                onClick={() => setMiniWindowOpenFor(null)}
                className="action-mini-window__close"
              >
                <i className="bi bi-x"></i>
              </button>
            </div>
            <div className="action-mini-window__content">
              <div className="action-mini-window__grid">
                {/* Audio Podcast button - Top Left */}
                <button 
                  onClick={async () => {
                    try {
                      console.log('=== AUDIO PODCAST BUTTON CLICKED ===');
                      const page = pages.find(p => p.id === miniWindowOpenFor);
                      setMiniWindowOpenFor(null); // Close mini window
                      
                      if (page) {
                        const documentName = page.filename || page.title;
                        console.log('Generating audio podcast for:', documentName);
                        
                        setAudioPodcastLoading(true); // Show loading indicator
                        
                        const response = await fetch('http://localhost:8001/audio-podcast', {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                          },
                          body: JSON.stringify({
                            document_name: documentName,
                            notebook_id: currentNotebook?.id || 1
                          }),
                        });
                        
                        if (response.ok) {
                          const result = await response.json();
                          console.log('Audio podcast generated:', result);
                          
                          // Trigger a refresh of the chat history to show new audio
                          if (window.refreshChatHistory) {
                            window.refreshChatHistory();
                          }
                        } else {
                          const errorData = await response.json();
                          console.error('Audio podcast generation failed:', errorData.detail || 'Unknown error');
                        }
                      }
                    } catch (error) {
                      console.error('Audio podcast error:', error);
                    } finally {
                      setAudioPodcastLoading(false); // Hide loading indicator
                    }
                  }} 
                  title="Generate Audio Podcast" 
                  className="action-mini-window__button"
                  disabled={audioPodcastLoading}
                >
                  {audioPodcastLoading ? (
                    <i className="bi bi-hourglass-split rotating-icon"></i>
                  ) : (
                    <i className="bi bi-mic-fill"></i>
                  )}
                  <span>{audioPodcastLoading ? 'Generating...' : 'Audio Podcast'}</span>
                </button>
                
                {/* Flowchart button */}
                <button 
                  onClick={() => {
                    setMiniWindowOpenFor(null); // Close mini window
                    console.log('=== MINDMAP BUTTON CLICKED ===');
                    const page = pages.find(p => p.id === miniWindowOpenFor);
                    if (page) {
                      console.log('Page filename:', page.filename);
                      console.log('Page title:', page.title);
                      console.log('Full page object:', page);
                      console.log('onMindmapClick function available:', !!onMindmapClick);
                      console.log('currentNotebook:', currentNotebook);
                      console.log('currentNotebook?.id:', currentNotebook?.id);
                      
                      const documentName = page.filename || page.title;
                      if (onMindmapClick && documentName) {
                        console.log('Calling onMindmapClick with:', currentNotebook?.id, documentName);
                        onMindmapClick(currentNotebook?.id, documentName);
                      } else {
                        console.error('Cannot call onMindmapClick:', {
                          onMindmapClickAvailable: !!onMindmapClick,
                          filename: page.filename,
                          title: page.title,
                          documentName: documentName,
                          notebookId: currentNotebook?.id
                        });
                      }
                    }
                  }} 
                  title="Generate Flowchart" 
                  className="action-mini-window__button"
                >
                  <i className="bi bi-diagram-3"></i>
                  <span>Flowchart</span>
                </button>
                
                {/* Visual Podcast button */}
                <button 
                  onClick={async () => {
                    try {
                      console.log('=== VISUAL PODCAST BUTTON CLICKED ===');
                      const page = pages.find(p => p.id === miniWindowOpenFor);
                      setMiniWindowOpenFor(null); // Close mini window
                      
                      if (page) {
                        console.log('Page filename:', page.filename);
                        console.log('Page title:', page.title);
                        console.log('Full page object:', page);
                        console.log('onVisualPodcastClick function available:', !!onVisualPodcastClick);
                        console.log('currentNotebook:', currentNotebook);
                        console.log('currentNotebook?.id:', currentNotebook?.id);
                        
                        const documentName = page.filename || page.title;
                        if (onVisualPodcastClick && documentName) {
                          console.log('Calling onVisualPodcastClick with:', currentNotebook?.id, documentName);
                          
                          // Start loading
                          setVisualPodcastLoading(true);
                          if (onVisualPodcastLoadingChange) {
                            onVisualPodcastLoadingChange(true);
                          }
                          
                          // Call the handler and wait for modal to open
                          await onVisualPodcastClick(currentNotebook?.id, documentName);
                          
                          // Clear loading state after the call completes
                          setVisualPodcastLoading(false);
                          if (onVisualPodcastLoadingChange) {
                            onVisualPodcastLoadingChange(false);
                          }
                        } else {
                          console.error('Cannot call onVisualPodcastClick:', {
                            onVisualPodcastClickAvailable: !!onVisualPodcastClick,
                            filename: page.filename,
                            title: page.title,
                            documentName: documentName,
                            notebookId: currentNotebook?.id
                          });
                        }
                      }
                    } catch (error) {
                      console.error('Visual podcast error:', error);
                      setVisualPodcastLoading(false);
                      if (onVisualPodcastLoadingChange) {
                        onVisualPodcastLoadingChange(false);
                      }
                    }
                  }} 
                  title="Visual Podcast (AI-Generated Slides)" 
                  className="action-mini-window__button"
                  disabled={visualPodcastLoading}
                >
                  {visualPodcastLoading ? (
                    <>
                      <i className="bi bi-arrow-clockwise loading-spin"></i>
                      <span>Generating...</span>
                    </>
                  ) : (
                    <>
                      <i className="bi bi-camera-reels"></i>
                      <span>Visual Podcast</span>
                    </>
                  )}
                </button>
                
                {/* Web Search button - Bottom Left */}
                <button 
                  onClick={async () => {
                    try {
                      const page = pages.find(p => p.id === miniWindowOpenFor);
                      setMiniWindowOpenFor(null); // Close window after getting page info
                      
                      if (page) {
                        const documentName = page.filename || page.title;
                        console.log('Starting web search for:', documentName);
                        
                        // Start loading
                        setWebSearchLoading(true);
                        
                        const response = await fetch('http://localhost:8001/web-search', {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                          },
                          body: JSON.stringify({
                            document_name: documentName,
                            notebook_id: currentNotebook?.id || 1
                          }),
                        });
                        
                        if (response.ok) {
                          const result = await response.json();
                          console.log('Web search results:', result);
                          
                          // Trigger a refresh of the chat history to show new messages
                          if (window.refreshChatHistory) {
                            window.refreshChatHistory();
                          }
                        } else {
                          const errorData = await response.json();
                          console.error('Web search failed:', errorData.detail || 'Unknown error');
                        }
                      } else {
                        console.error('Could not find document information');
                      }
                    } catch (error) {
                      console.error('Web search error:', error);
                    } finally {
                      // Stop loading
                      setWebSearchLoading(false);
                    }
                  }} 
                  title="Web Search" 
                  className="action-mini-window__button"
                  disabled={webSearchLoading}
                >
                  {webSearchLoading ? (
                    <>
                      <i className="bi bi-arrow-clockwise loading-spin"></i>
                      <span>Searching...</span>
                    </>
                  ) : (
                    <>
                      <i className="bi bi-globe2"></i>
                      <span>Web Search</span>
                    </>
                  )}
                </button>
                
                {/* Video button - Bottom Right */}
                <button 
                  onClick={() => {
                    console.log('=== VIDEO BUTTON CLICKED ===');
                    const page = pages.find(p => p.id === miniWindowOpenFor);
                    setMiniWindowOpenFor(null); // Close mini window
                    
                    if (page) {
                      console.log('Page filename:', page.filename);
                      console.log('Page title:', page.title);
                      console.log('Full page object:', page);
                      console.log('onVideosClick function available:', !!onVideosClick);
                      console.log('currentNotebook:', currentNotebook);
                      console.log('currentNotebook?.id:', currentNotebook?.id);
                      
                      const documentName = page.filename || page.title;
                      if (onVideosClick && documentName) {
                        console.log('Calling onVideosClick with:', currentNotebook?.id, documentName);
                        onVideosClick(currentNotebook?.id, documentName);
                      } else {
                        console.error('Cannot call onVideosClick:', {
                          onVideosClickAvailable: !!onVideosClick,
                          filename: page.filename,
                          title: page.title,
                          documentName: documentName,
                          notebookId: currentNotebook?.id
                        });
                      }
                    }
                  }} 
                  title="Educational Videos" 
                  className="action-mini-window__button"
                >
                  <i className="bi bi-youtube"></i>
                  <span>Video</span>
                </button>

                {/* Quiz Mode button - Bottom Left */}
                <button 
                  onClick={() => {
                    console.log('=== QUIZ MODE BUTTON CLICKED ===');
                    const page = pages.find(p => p.id === miniWindowOpenFor);
                    setMiniWindowOpenFor(null); // Close mini window
                    
                    if (page) {
                      console.log('onQuizClick function available:', !!onQuizClick);
                      console.log('currentNotebook:', currentNotebook);
                      console.log('currentNotebook?.id:', currentNotebook?.id);
                      
                      if (onQuizClick && currentNotebook?.id) {
                        console.log('Calling onQuizClick with notebook ID:', currentNotebook.id);
                        onQuizClick(currentNotebook.id);
                      } else {
                        console.error('Cannot call onQuizClick:', {
                          onQuizClickAvailable: !!onQuizClick,
                          notebookId: currentNotebook?.id
                        });
                      }
                    }
                  }} 
                  title="Quiz Mode - Test Your Knowledge" 
                  className="action-mini-window__button action-mini-window__button--quiz"
                >
                  <i className="bi bi-question-circle"></i>
                  <span>Quiz Mode</span>
                </button>

                {/* Flashcards button - Bottom Right */}
                <button 
                  onClick={() => {
                    console.log('=== FLASHCARDS BUTTON CLICKED ===');
                    setMiniWindowOpenFor(null); // Close mini window
                    if (onFlashcardClick && currentNotebook) {
                      onFlashcardClick(currentNotebook.id);
                    }
                  }} 
                  title="Flashcards - Study with AI-Generated Cards" 
                  className="action-mini-window__button action-mini-window__button--flashcard"
                >
                  <i className="bi bi-card-text"></i>
                  <span>Flashcards</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
