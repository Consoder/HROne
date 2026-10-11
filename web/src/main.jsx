import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './ui.jsx';
import './style.css';

// React mounts the attendance experience into the single page root.
createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
