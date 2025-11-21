import React, { useState } from 'react';
import './Sidebar.css';

export default function Sidebar({ notebooks, currentNotebookId, onSelectNotebook, onAddNotebook, onDeleteNotebook, onRenameNotebook, onToggleSidebar, onOpenWebsiteModal }) {
  const [editingId, setEditingId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const handleEditStart = (notebook) => {
    setEditingId(notebook.id);
    setEditingTitle(notebook.title);
  };

  const handleEditSave = () => {
    if (editingTitle.trim() && onRenameNotebook) {
      onRenameNotebook(editingId, editingTitle.trim());
    }
    setEditingId(null);
    setEditingTitle('');
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditingTitle('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleEditSave();
    } else if (e.key === 'Escape') {
      handleEditCancel();
    }
  };

  const handleBlur = () => {
    // Save on blur instead of canceling
    handleEditSave();
  };
  return (
    <aside className="Sidebar" aria-label="Notebooks sidebar">
      <div className="Sidebar__header">
        <div className="Sidebar__headerTop">
          <button 
            onClick={onToggleSidebar} 
            className="Sidebar__hamburger"
            title="Hide sidebar"
            aria-label="Hide sidebar"
          >
            <i className="bi bi-layout-sidebar-inset"></i>
          </button>
        </div>
        <div className="Sidebar__buttons">
          <button className="addBtn" onClick={onAddNotebook} title="Add Notebook">
            <i className="bi bi-plus-lg"></i>
            <span>New Notebook</span>
          </button>
          <button className="addBtn" onClick={onOpenWebsiteModal} title="Add Website / Link">
            <i className="bi bi-link-45deg"></i>
            <span>New Website / Link</span>
          </button>
        </div>
      </div>
      <nav className="Sidebar__list" aria-label="Notebook list">
        {notebooks.map(nb => (
          <div key={nb.id} className={`Sidebar__itemWrapper ${nb.id === currentNotebookId ? 'is-active' : ''}`}>
            {editingId === nb.id ? (
              <input
                type="text"
                value={editingTitle}
                onChange={(e) => setEditingTitle(e.target.value)}
                onKeyDown={handleKeyPress}
                onBlur={handleBlur}
                className="Sidebar__editInput"
                autoFocus
              />
            ) : (
              <button
                onClick={() => onSelectNotebook(nb.id)}
                className="Sidebar__item"
              >
                <span className="Sidebar__dot" />
                <span className="Sidebar__title">{nb.title || 'Untitled'}</span>
              </button>
            )}
            <div className="Sidebar__actions">
              <button 
                onClick={() => handleEditStart(nb)} 
                className="Sidebar__edit"
                title="Rename notebook"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z" />
                </svg>
              </button>
              <button 
                onClick={() => onDeleteNotebook(nb.id)} 
                className="Sidebar__delete"
                title="Delete notebook"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                  <path fillRule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                </svg>
              </button>
            </div>
          </div>
        ))}
        {notebooks.length === 0 && (
          <div className="Sidebar__empty">No notebooks yet.</div>
        )}
      </nav>
    </aside>
  );
}
