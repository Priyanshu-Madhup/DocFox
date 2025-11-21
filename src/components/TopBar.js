import React from 'react';
import './TopBar.css';

export default function TopBar({ notebookTitle, onTitleChange, darkMode, onToggleDark, sidebarOpen, onToggleSidebar, rightSidebarOpen, onToggleRightSidebar }) {
  return (
    <div className="TopBar">
      <div className="TopBar__left">
        {!sidebarOpen && (
          <button 
            onClick={onToggleSidebar} 
            className="TopBar__hamburger"
            title="Show sidebar"
            aria-label="Show sidebar"
          >
            <i className="bi bi-layout-sidebar-inset"></i>
          </button>
        )}
        <input
          className="TopBar__title"
          value={notebookTitle}
          onChange={e => onTitleChange(e.target.value)}
          placeholder="Notebook title..."
          aria-label="Notebook title"
        />
      </div>
      <div className="TopBar__actions">
        <div className="TopBar__rightHamburgerSpace">
          {!rightSidebarOpen && (
            <button 
              onClick={onToggleRightSidebar} 
              className="TopBar__hamburger"
              title="Show right sidebar"
              aria-label="Show right sidebar"
            >
              <i className="bi bi-layout-sidebar-inset-reverse"></i>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
