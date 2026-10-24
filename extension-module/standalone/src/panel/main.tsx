import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HorizonApp } from './horizon/HorizonApp';
import './index.css';

createRoot(document.getElementById('root')!).render(<StrictMode><HorizonApp /></StrictMode>);
