import React, { useEffect, useState } from 'react';
import './VisualPodcastModal.css';

const VisualPodcastModal = ({ isOpen, onClose, notebookId, documentName, onLoadingChange }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [videoUrl, setVideoUrl] = useState(null);
  const [error, setError] = useState('');
  const [slides, setSlides] = useState([]);

  console.log('VisualPodcastModal rendered with:', { isOpen, notebookId, documentName });

  useEffect(() => {
    console.log('VisualPodcastModal useEffect:', { isOpen, notebookId, documentName });
    if (isOpen && notebookId && documentName) {
      // Check if we have saved data from chat history
      if (window.savedVisualPodcastData) {
        console.log('Loading saved visual podcast data:', window.savedVisualPodcastData);
        const savedData = window.savedVisualPodcastData;
        
        // Load the saved data
        setSlides(savedData.slides || []);
        setVideoUrl(savedData.video_url || null);
        setIsLoading(false);
        
        // Clear the saved data
        window.savedVisualPodcastData = null;
      } else {
        // No saved data, generate new visual podcast
        // Clear previous data
        setVideoUrl(null);
        setSlides([]);
        setError('');
        
        // Start visual podcast generation
        setTimeout(() => {
          generateVisualPodcast();
        }, 100);
      }
    }
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, notebookId, documentName]);

  if (!isOpen) {
    return null;
  }

  const generateVisualPodcast = async () => {
    setIsLoading(true);
    setError('');
    console.log('Starting visual podcast generation for:', { notebookId, documentName });
    
    try {
      const response = await fetch('http://localhost:8001/visual-podcast', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          document_name: documentName,
          notebook_id: notebookId
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Visual podcast generation failed');
      }

      const data = await response.json();
      console.log('Visual podcast response:', data);
      
      if (data.success) {
        setSlides(data.slides || []);
        setVideoUrl(data.video_url || null);
        
        // Trigger a refresh of the chat history to show new messages
        if (window.refreshChatHistory) {
          window.refreshChatHistory();
        }
      } else {
        setError(data.message || 'Failed to generate visual podcast.');
      }

    } catch (error) {
      console.error('Visual podcast generation error:', error);
      setError(error.message || 'Failed to generate visual podcast');
    } finally {
      setIsLoading(false);
      // Notify parent that loading is complete
      if (onLoadingChange) {
        onLoadingChange(false);
      }
    }
  };

  return (
    <div className="visual-podcast-modal-overlay" onClick={onClose}>
      <div className="visual-podcast-modal" onClick={(e) => e.stopPropagation()}>
        <div className="visual-podcast-modal__header">
          <div className="visual-podcast-modal__title">
            <i className="bi bi-camera-reels"></i>
            <span>Visual Podcast</span>
            {documentName && <small>for {documentName}</small>}
          </div>
          <button className="visual-podcast-modal__close" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>

        <div className="visual-podcast-modal__content">
          {isLoading ? (
            <div className="visual-podcast-modal__loading">
              <div className="loading-spinner"></div>
              <p>Generating AI-powered visual podcast...</p>
              <p className="loading-subtitle">Creating slides, audio narration, and video</p>
            </div>
          ) : error ? (
            <div className="visual-podcast-modal__error">
              <i className="bi bi-exclamation-triangle"></i>
              <h3>Generation Failed</h3>
              <p>{error}</p>
              <button onClick={generateVisualPodcast} className="retry-button">
                <i className="bi bi-arrow-clockwise"></i>
                Try Again
              </button>
            </div>
          ) : videoUrl ? (
            <div className="video-player-container">
              <div className="video-player">
                <video 
                  key={videoUrl}
                  controls 
                  controlsList=""
                  preload="auto"
                  playsInline
                  autoPlay={false}
                  src={videoUrl}
                  style={{ width: '100%', height: '100%', borderRadius: '8px' }}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
              
              <div className="video-actions">
                <a 
                  href={videoUrl} 
                  download="visual-podcast.mp4"
                  className="download-video-button"
                >
                  <i className="bi bi-download"></i>
                  Download MP4 Video
                </a>
                
                <button 
                  onClick={generateVisualPodcast} 
                  className="regenerate-button"
                >
                  <i className="bi bi-arrow-clockwise"></i>
                  Generate New Video
                </button>
              </div>
            </div>
          ) : (
            <div className="no-video">
              <i className="bi bi-camera-reels"></i>
              <h3>No Video Generated</h3>
              <p>No visual podcast could be generated for this document.</p>
              <button onClick={generateVisualPodcast} className="retry-button">
                <i className="bi bi-arrow-clockwise"></i>
                Generate Video
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VisualPodcastModal;
