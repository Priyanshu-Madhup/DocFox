import React, { useEffect, useState } from 'react';
import './VideosModal.css';

const VideosModal = ({ isOpen, onClose, notebookId, documentName }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [videos, setVideos] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [error, setError] = useState('');
  const [videoLoading, setVideoLoading] = useState(false);

  console.log('VideosModal rendered with:', { isOpen, notebookId, documentName });

  useEffect(() => {
    console.log('VideosModal useEffect:', { isOpen, notebookId, documentName });
    if (isOpen && notebookId && documentName) {
      // Clear previous data
      setVideos([]);
      setSearchQuery('');
      setSelectedVideo(null);
      setError('');
      
      // Start video search
      setTimeout(() => {
        searchVideos();
      }, 100);
    }
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, notebookId, documentName]);

  if (!isOpen) {
    return null;
  }

  const searchVideos = async () => {
    setIsLoading(true);
    setError('');
    console.log('Starting video search for:', { notebookId, documentName });
    
    try {
      const response = await fetch('http://localhost:8001/video-search', {
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
        throw new Error(errorData.detail || 'Video search failed');
      }

      const data = await response.json();
      console.log('Video search response:', data);
      
      if (data.success && data.videos && data.videos.length > 0) {
        setVideos(data.videos);
        setSearchQuery(data.query || '');
        
        // Trigger a refresh of the chat history to show new messages
        if (window.refreshChatHistory) {
          window.refreshChatHistory();
        }
      } else {
        // No videos found or API failed
        setVideos([]);
        setSearchQuery(data.query || searchQuery);
        setError(data.message || 'No educational videos found for this topic at the moment.');
      }

    } catch (error) {
      console.error('Video search error:', error);
      setError(error.message || 'Failed to search for videos');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVideoSelect = (video) => {
    setVideoLoading(true);
    setSelectedVideo(video);
    // Reset loading state after a short delay to allow iframe to load
    setTimeout(() => setVideoLoading(false), 1000);
  };

  const handleBackToList = () => {
    setSelectedVideo(null);
    setVideoLoading(false);
  };

  const formatDuration = (duration) => {
    if (!duration) return '';
    return duration;
  };

  return (
    <div className="videos-modal-overlay" onClick={onClose}>
      <div className="videos-modal" onClick={(e) => e.stopPropagation()}>
        <div className="videos-modal__header">
          <div className="videos-modal__title">
            <i className="bi bi-youtube"></i>
            <span>Educational Videos</span>
            {documentName && <small>for {documentName}</small>}
          </div>
          <button className="videos-modal__close" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>

        <div className="videos-modal__content">
          {isLoading ? (
            <div className="videos-modal__loading">
              <div className="loading-spinner"></div>
              <p>Searching for educational videos...</p>
              <p className="loading-subtitle">Finding relevant content based on your document</p>
            </div>
          ) : error ? (
            <div className="videos-modal__error">
              <i className="bi bi-exclamation-triangle"></i>
              <h3>Search Failed</h3>
              <p>{error}</p>
              <button onClick={searchVideos} className="retry-button">
                <i className="bi bi-arrow-clockwise"></i>
                Try Again
              </button>
            </div>
          ) : selectedVideo ? (
            <div className="video-player-container">
              <div className="video-player-header">
                <button onClick={handleBackToList} className="back-button">
                  <i className="bi bi-arrow-left"></i>
                  Back to Videos
                </button>
                <h3>{selectedVideo.title}</h3>
              </div>
              <div className="video-player">
                {videoLoading && (
                  <div className="video-loading">
                    <div className="loading-spinner"></div>
                    <p>Loading video...</p>
                  </div>
                )}
                <iframe
                  src={`https://www.youtube.com/embed/${selectedVideo.videoId}?autoplay=0&rel=0&modestbranding=1`}
                  title={selectedVideo.title}
                  frameBorder="0"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  onLoad={() => setVideoLoading(false)}
                  style={{ display: videoLoading ? 'none' : 'block' }}
                ></iframe>
              </div>
              <div className="video-info">
                <p><strong>Duration:</strong> {formatDuration(selectedVideo.duration)}</p>
                {selectedVideo.date && <p><strong>Published:</strong> {selectedVideo.date}</p>}
                <a href={selectedVideo.url} target="_blank" rel="noopener noreferrer" className="youtube-link">
                  <i className="bi bi-box-arrow-up-right"></i>
                  Watch on YouTube
                </a>
              </div>
            </div>
          ) : (
            <div className="videos-list-container">
              {searchQuery && (
                <div className="search-info">
                  <p><strong>Search Query:</strong> {searchQuery}</p>
                  <p>Found {videos.length} educational videos</p>
                </div>
              )}
              
              {videos.length > 0 ? (
                <div className="videos-grid">
                  {videos.map((video, index) => (
                    <div 
                      key={index} 
                      className="video-card" 
                      onClick={() => handleVideoSelect(video)}
                    >
                      <div className="video-thumbnail">
                        <img 
                          src={video.thumbnail} 
                          alt={video.title}
                          onError={(e) => {
                            // First fallback: try hqdefault
                            if (e.target.src.includes('mqdefault')) {
                              e.target.src = e.target.src.replace('mqdefault', 'hqdefault');
                            } 
                            // Second fallback: try default thumbnail
                            else if (e.target.src.includes('hqdefault')) {
                              e.target.src = e.target.src.replace('hqdefault', 'default');
                            }
                            // Final fallback: use placeholder
                            else {
                              e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjY2NjIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxOCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPllvdVR1YmUgVmlkZW88L3RleHQ+PC9zdmc+';
                            }
                          }}
                        />
                        <div className="video-play-overlay">
                          <i className="bi bi-play-fill"></i>
                        </div>
                        {video.duration && (
                          <div className="video-duration">
                            {formatDuration(video.duration)}
                          </div>
                        )}
                      </div>
                      <div className="video-details">
                        <h4 className="video-title">{video.title}</h4>
                        {video.date && (
                          <p className="video-date">{video.date}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-videos">
                  <i className="bi bi-camera-video"></i>
                  <h3>No Videos Found</h3>
                  <p>No educational videos found for this document.</p>
                  <button onClick={searchVideos} className="retry-button">
                    <i className="bi bi-arrow-clockwise"></i>
                    Search Again
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VideosModal;
