import React from 'react';
import './Navbar.css';

const Navbar = () => {
  return (
    <div className="navbar">
      <div className="navbar__left">
        <div className="navbar__logo">
          <span className="navbar__logoText">DocFox</span>
        </div>
      </div>
      
      <div className="navbar__center">
        {/* Title removed as requested */}
      </div>
      
      <div className="navbar__right">
        {/* Mindmap button moved to individual PDF items */}
      </div>
    </div>
  );
};

export default Navbar;
