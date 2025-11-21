// Simple notebook state management without authentication
import { useEffect, useState, useCallback } from 'react';

export function useNotebooks() {
  const [notebooks, setNotebooks] = useState([]);
  const [currentNotebookId, setCurrentNotebookId] = useState(null);
  const [currentPageId, setCurrentPageId] = useState(null);

  // Load notebooks from backend
  // Create default notebook
  const createDefaultNotebook = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:8001/notebooks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: 'My First Notebook'
        }),
      });
      
      if (response.ok) {
        const newNotebook = await response.json();
        newNotebook.chat_history = [];
        setNotebooks([newNotebook]);
        setCurrentNotebookId(newNotebook.id);
      }
    } catch (error) {
      console.error('Error creating default notebook:', error);
    }
  }, []);

  const loadNotebooks = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:8001/notebooks');
      if (response.ok) {
        const backendNotebooks = await response.json();
        if (backendNotebooks.length > 0) {
          // Sort notebooks by creation time (most recent first)
          const sortedNotebooks = backendNotebooks.sort((a, b) => {
            const timeA = new Date(a.updated_at || a.created_at || 0).getTime();
            const timeB = new Date(b.updated_at || b.created_at || 0).getTime();
            return timeB - timeA; // Most recent first
          });
          setNotebooks(sortedNotebooks);
          if (!currentNotebookId) {
            setCurrentNotebookId(sortedNotebooks[0].id);
          }
        } else {
          // No notebooks on backend, create default one
          await createDefaultNotebook();
        }
      } else {
        // Backend not available, use sample data
        const sampleNotebooks = [
          {
            id: 1,
            title: 'My First Notebook',
            pages: [],
            chat_history: [],
            created_at: new Date().toISOString()
          }
        ];
        setNotebooks(sampleNotebooks);
        setCurrentNotebookId(1);
      }
    } catch (error) {
      console.error('Error loading notebooks:', error);
      // Backend not available, use sample data
      const sampleNotebooks = [
        {
          id: 1,
          title: 'My First Notebook', 
          pages: [],
          chat_history: [],
          created_at: new Date().toISOString()
        }
      ];
      setNotebooks(sampleNotebooks);
      setCurrentNotebookId(1);
    }
  }, [currentNotebookId, createDefaultNotebook]);

  // Load initial data
  useEffect(() => {
    loadNotebooks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh a single notebook from backend (useful after server-side changes like processing PDFs)
  const refreshNotebook = useCallback(async (id) => {
    if (!id) return;
    try {
      const response = await fetch(`http://localhost:8001/notebooks/${id}`);
      if (response.ok) {
        const backendNotebook = await response.json();
        // Replace or add the notebook in local state
        setNotebooks(nbs => {
          const exists = nbs.some(n => n.id === backendNotebook.id);
          if (exists) {
            return nbs.map(n => n.id === backendNotebook.id ? backendNotebook : n);
          }
          return [backendNotebook, ...nbs];
        });
      }
    } catch (err) {
      console.error('Error refreshing notebook:', err);
    }
  }, []);

  // Keep the current notebook in sync with backend when switching
  useEffect(() => {
    if (currentNotebookId) {
      refreshNotebook(currentNotebookId);
    }
  }, [currentNotebookId, refreshNotebook]);

  const setNotebookTitle = useCallback((id, title) => {
    setNotebooks(nbs => nbs.map(n => n.id === id ? { ...n, title, updatedAt: Date.now() } : n));
  }, []);

  const renameNotebook = useCallback(async (id, title) => {
    try {
      console.log(`Renaming notebook ${id} to: ${title}`);
      
      // Call backend API to update the notebook title
      const response = await fetch(`http://localhost:8001/notebooks/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: title
        }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to rename notebook');
      }
      
      const updatedNotebook = await response.json();
      console.log('Backend returned updated notebook:', updatedNotebook);
      
      // Update local state after successful backend update
      setNotebooks(nbs => nbs.map(n => n.id === id ? { ...n, title, updated_at: updatedNotebook.updated_at } : n));
      
      console.log('Local state updated successfully');
    } catch (error) {
      console.error('Error renaming notebook:', error);
      // You might want to show a user-friendly error message here
    }
  }, []);

  const addNotebook = useCallback(async (title = 'New Notebook') => {
    try {
      const response = await fetch('http://localhost:8001/notebooks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: title
        }),
      });
      
      if (response.ok) {
        const newNotebook = await response.json();
        newNotebook.chat_history = [];
        setNotebooks(nbs => [newNotebook, ...nbs]);
        setCurrentNotebookId(newNotebook.id);
        setCurrentPageId(null);
      } else {
        // Fallback to local creation
        const newNotebook = {
          id: Date.now(),
          title: title,
          pages: [],
          chat_history: [],
          created_at: new Date().toISOString()
        };
        setNotebooks(nbs => [newNotebook, ...nbs]);
        setCurrentNotebookId(newNotebook.id);
        setCurrentPageId(null);
      }
    } catch (error) {
      console.error('Error creating notebook:', error);
      // Fallback to local creation
      const newNotebook = {
        id: Date.now(),
        title: title,
        pages: [],
        chat_history: [],
        created_at: new Date().toISOString()
      };
      setNotebooks(nbs => [newNotebook, ...nbs]);
      setCurrentNotebookId(newNotebook.id);
      setCurrentPageId(null);
    }
  }, []);

  const addPage = useCallback((fileOrTitleOrFiles) => {
    if (!currentNotebookId) return;
    
    // Handle array of files (multiple PDF upload)
    if (Array.isArray(fileOrTitleOrFiles)) {
      const newPages = fileOrTitleOrFiles.map(file => ({
        id: Date.now() + Math.random(), // Ensure unique IDs
        title: file.name,
        type: 'pdf',
        file: file // Store the file for processing
      }));
      
      setNotebooks(nbs => nbs.map(n => {
        if (n.id !== currentNotebookId) return n;
        // Set the first uploaded PDF as current page
        if (newPages.length > 0) {
          setCurrentPageId(newPages[0].id);
        }
        return { ...n, pages: [...newPages, ...n.pages], updatedAt: Date.now() };
      }));
      return;
    }
    
    // Handle single file or title (existing functionality)
    const newPage = {
      id: Date.now(),
      title: fileOrTitleOrFiles instanceof File ? fileOrTitleOrFiles.name : (fileOrTitleOrFiles || 'New Page'),
      type: fileOrTitleOrFiles instanceof File ? 'pdf' : 'text',
      file: fileOrTitleOrFiles instanceof File ? fileOrTitleOrFiles : null // Store the file for processing
    };
    
    setNotebooks(nbs => nbs.map(n => {
      if (n.id !== currentNotebookId) return n;
      setCurrentPageId(newPage.id);
      return { ...n, pages: [newPage, ...n.pages], updatedAt: Date.now() };
    }));
  }, [currentNotebookId]);

  const updatePage = useCallback((page) => {
    if (!currentNotebookId) return;
    setNotebooks(nbs => nbs.map(n => {
      if (n.id !== currentNotebookId) return n;
      return {
        ...n,
        pages: n.pages.map(p => p.id === page.id ? page : p),
        updatedAt: Date.now()
      };
    }));
  }, [currentNotebookId]);

  const deletePage = useCallback(async (pageId) => {
    if (!currentNotebookId) return;
    
    // Find the page to be deleted to get its filename
    const notebook = notebooks.find(n => n.id === currentNotebookId);
    const pageToDelete = notebook?.pages.find(p => p.id === pageId);
    
    // If it's a PDF, call backend API to remove from vector database
    if (pageToDelete?.type === 'pdf' && pageToDelete?.filename) {
      try {
        const response = await fetch('http://localhost:8001/remove-document', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            document_name: pageToDelete.filename,
            notebook_id: currentNotebookId
          }),
        });
        
        if (response.ok) {
          const result = await response.json();
          console.log(`Successfully removed document: ${result.message}`);
        } else {
          console.error('Failed to remove document from backend');
        }
      } catch (error) {
        console.error('Error calling remove-document API:', error);
      }
    }
    
    // Update frontend state
    setNotebooks(nbs => nbs.map(n => {
      if (n.id !== currentNotebookId) return n;
      const pages = n.pages.filter(p => p.id !== pageId);
      if (currentPageId === pageId) setCurrentPageId(pages[0]?.id || null);
      return { ...n, pages, updatedAt: Date.now() };
    }));
  }, [currentNotebookId, currentPageId, notebooks]);

  const deleteNotebook = useCallback(async (notebookId) => {
    try {
      // Call backend API to delete the notebook
      const response = await fetch(`http://localhost:8001/notebooks/${notebookId}`, {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete notebook');
      }
      
      // Update local state after successful backend deletion
      setNotebooks(nbs => {
        const filtered = nbs.filter(n => n.id !== notebookId);
        
        // If we're deleting the current notebook, switch to another one
        if (currentNotebookId === notebookId) {
          if (filtered.length > 0) {
            setCurrentNotebookId(filtered[0].id);
            setCurrentPageId(filtered[0].pages[0]?.id || null);
          } else {
            // No notebooks left, create a new one
            const newNotebook = {
              id: Date.now(),
              title: 'New Notebook',
              pages: [],
              chat_history: [],
              updatedAt: Date.now()
            };
            setCurrentNotebookId(newNotebook.id);
            setCurrentPageId(null);
            return [newNotebook];
          }
        }
        
        return filtered;
      });
    } catch (error) {
      console.error('Error deleting notebook:', error);
      // You might want to show a user-friendly error message here
    }
  }, [currentNotebookId]);

  const currentNotebook = notebooks.find(n => n.id === currentNotebookId) || null;
  const currentPage = currentNotebook?.pages.find(p => p.id === currentPageId) || null;

  return {
    notebooks,
    currentNotebook,
    currentNotebookId,
    setCurrentNotebookId,
    setNotebookTitle,
    renameNotebook,
    addNotebook,
    deleteNotebook,
    addPage,
    currentPage,
    currentPageId,
    setCurrentPageId,
    updatePage,
    deletePage
    ,
    refreshNotebook
  };
}
