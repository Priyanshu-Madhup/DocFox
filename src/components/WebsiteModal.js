import React, { useState } from 'react';
import './WebsiteModal.css';

export default function WebsiteModal({ isOpen, onClose, onCreateNotebook }) {
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!websiteUrl.trim()) {
      setError('Please enter a valid URL');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      // Validate URL format
      new URL(websiteUrl);
      // Call the scraping function
      const result = await scrapeWebsite(websiteUrl);
      // Create notebook with scraped content
      onCreateNotebook(result);
      // Reset and close modal
      setWebsiteUrl('');
      onClose();
    } catch (err) {
      setError('Failed to scrape website. Please check the URL and try again.');
      console.error('Scraping error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const scrapeWebsite = async (url) => {
    // FIXED: Changed port from 8000 to 8001 to match your FastAPI backend
    const response = await fetch('http://localhost:8001/scrape-website', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    });

    if (!response.ok) {
      throw new Error('Failed to scrape website');
    }

    return response.json();
  };

  const handleClose = () => {
    setWebsiteUrl('');
    setError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="website-modal-overlay">
      <div className="website-modal">
        <div className="website-modal__header">
          <h3>Add Website / Link</h3>
          <button 
            onClick={handleClose}
            className="website-modal__close"
            type="button"
          >
            <i className="bi bi-x"></i>
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="website-modal__form">
          <div className="website-modal__content">
            <label htmlFor="website-url" className="website-modal__label">
              Website URL
            </label>
            <input
              id="website-url"
              type="url"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              placeholder="https://example.com"
              className="website-modal__input"
              disabled={isLoading}
              required
            />
            
            {error && (
              <div className="website-modal__error">
                <i className="bi bi-exclamation-triangle"></i>
                {error}
              </div>
            )}
          </div>
          
          <div className="website-modal__actions">
            <button 
              type="button" 
              onClick={handleClose}
              className="website-modal__button website-modal__button--secondary"
              disabled={isLoading}
            >
              Cancel
            </button>
            <button 
              type="submit"
              className="website-modal__button website-modal__button--primary"
              disabled={isLoading || !websiteUrl.trim()}
            >
              {isLoading ? (
                <>
                  <i className="bi bi-arrow-clockwise loading-spin"></i>
                  Scraping...
                </>
              ) : (
                <>
                  <i className="bi bi-download"></i>
                  Create Notebook
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}