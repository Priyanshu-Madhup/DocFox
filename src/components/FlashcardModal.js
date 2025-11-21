import React, { useState, useEffect } from 'react';
import './FlashcardModal.css';

const FlashcardModal = ({ isOpen, onClose, notebookId }) => {
  const [flashcards, setFlashcards] = useState([]);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen && notebookId) {
      generateFlashcards();
    }
  }, [isOpen, notebookId]);

  useEffect(() => {
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, isFlipped, currentCardIndex, flashcards]);

  if (!isOpen) return null;

  const generateFlashcards = async () => {
    setIsGenerating(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:8001/flashcards/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          notebook_id: notebookId,
          num_flashcards: 50
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate flashcards');
      }

      const data = await response.json();
      setFlashcards(data.flashcards);
      setCurrentCardIndex(0);
      setIsFlipped(false);

    } catch (error) {
      console.error('Error generating flashcards:', error);
      setError(error.message || 'Failed to generate flashcards');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFlipCard = () => {
    setIsFlipped(!isFlipped);
  };

  const handleNextCard = () => {
    if (currentCardIndex < flashcards.length - 1) {
      setCurrentCardIndex(currentCardIndex + 1);
      setIsFlipped(false);
    }
  };

  const handlePrevCard = () => {
    if (currentCardIndex > 0) {
      setCurrentCardIndex(currentCardIndex - 1);
      setIsFlipped(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      handleFlipCard();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      handleNextCard();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      handlePrevCard();
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div className="flashcard-overlay" onClick={onClose}>
      <div className="flashcard-modal" onClick={(e) => e.stopPropagation()}>
        <div className="flashcard-header">
          <h2>Flashcards</h2>
          <button className="close-flashcards" onClick={onClose}>
            ✕
          </button>
        </div>

        {isGenerating ? (
          <div className="flashcard-loading">
            <div className="loading-spinner"></div>
            <p>Generating flashcards...</p>
          </div>
        ) : error ? (
          <div className="flashcard-error">
            <p>{error}</p>
            <button onClick={generateFlashcards}>Try Again</button>
          </div>
        ) : flashcards.length > 0 ? (
          <>
            <div className="flashcard-progress">
              <div className="progress-bar">
                <div 
                  className="progress-fill" 
                  style={{ width: `${((currentCardIndex + 1) / flashcards.length) * 100}%` }}
                />
              </div>
              <p className="card-counter">{currentCardIndex + 1} / {flashcards.length}</p>
            </div>

            <div className="flashcard-container">
              <div 
                className={`flashcard ${isFlipped ? 'flipped' : ''}`}
                onClick={handleFlipCard}
              >
                <div className="flashcard-front">
                  <div className="card-label">Question</div>
                  <div className="card-content">
                    {flashcards[currentCardIndex].front}
                  </div>
                  <div className="card-hint">Click or press Space to flip</div>
                </div>
                <div className="flashcard-back">
                  <div className="card-label">Answer</div>
                  <div className="card-content">
                    {flashcards[currentCardIndex].back}
                  </div>
                  <div className="card-category">
                    <span className="category-badge">
                      {flashcards[currentCardIndex].category}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flashcard-navigation">
              <button 
                className="nav-btn prev" 
                onClick={handlePrevCard}
                disabled={currentCardIndex === 0}
              >
                <span>←</span> Previous
              </button>
              
              <button 
                className="flip-btn" 
                onClick={handleFlipCard}
              >
                <span>⟲</span> Flip Card
              </button>
              
              <button 
                className="nav-btn next" 
                onClick={handleNextCard}
                disabled={currentCardIndex === flashcards.length - 1}
              >
                Next <span>→</span>
              </button>
            </div>

            <div className="keyboard-hints">
              <span>Space: Flip</span>
              <span>← / →: Navigate</span>
              <span>Esc: Close</span>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
};

export default FlashcardModal;
