import React, { useState } from 'react';
import './AIPanel.css';

// Placeholder AI panel (no real backend). Simulates responses.
export default function AIPanel({ currentPage }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [working, setWorking] = useState(false);

  const send = () => {
    if (!input.trim()) return;
    const userMsg = { id: Date.now() + '-u', role: 'user', content: input.trim() };
    setMessages(m => [...m, userMsg]);
    const prompt = input.trim();
    setInput('');
    setWorking(true);
    setTimeout(() => {
      const aiMsg = { id: Date.now() + '-a', role: 'ai', content: `AI draft based on page '${currentPage?.title || 'Untitled'}':\n\n` + prompt.split('').reverse().join('') };
      setMessages(m => [...m, aiMsg]);
      setWorking(false);
    }, 600);
  };

  return (
    <div className="AIPanel" aria-label="AI assistant panel">
      <div className="AIPanel__header">Assistant</div>
      <div className="AIPanel__messages">
        {messages.map(msg => (
          <div key={msg.id} className={"msg msg--" + msg.role}>{msg.content}</div>
        ))}
        {messages.length === 0 && <div className="placeholder">Ask a question about your notes.</div>}
      </div>
      <div className="AIPanel__inputRow">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={working ? 'Working...' : 'Ask or draft...'}
          disabled={working}
        />
        <button onClick={send} disabled={working} className="sendBtn">Send</button>
      </div>
    </div>
  );
}
