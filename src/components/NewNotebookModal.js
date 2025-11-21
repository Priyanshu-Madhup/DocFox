import React, { useState, useEffect } from 'react';
import './NewNotebookModal.css';

export default function NewNotebookModal({ isOpen, onClose, onConfirm }) {
  const [notebookName, setNotebookName] = useState('New Notebook');

  useEffect(() => {
    if (isOpen) {
      setNotebookName('New Notebook');
    }
  }, [isOpen]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const finalName = notebookName.trim() || 'New Notebook';
    onConfirm(finalName);
    onClose();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="new-notebook-modal-overlay" onClick={onClose}>
      <div className="new-notebook-modal" onClick={(e) => e.stopPropagation()}>
        <div className="new-notebook-modal-header">
          <h3>Create New Notebook</h3>
          <button 
            className="new-notebook-modal-close" 
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="new-notebook-modal-form">
          <div className="new-notebook-modal-body">
            <label htmlFor="notebook-name">Notebook Name:</label>
            <input
              id="notebook-name"
              type="text"
              value={notebookName}
              onChange={(e) => setNotebookName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter notebook name"
              autoFocus
              maxLength={100}
            />
          </div>
          
          <div className="new-notebook-modal-footer">
            <button 
              type="button" 
              className="new-notebook-modal-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="new-notebook-modal-confirm"
            >
              Create Notebook
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
