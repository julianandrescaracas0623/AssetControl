import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './index.css'
import App from './App.tsx'
import Componentes from './routes/dev/Componentes.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* Provisional hasta el enrutado de T3 (spec 001b). */}
    {window.location.pathname === '/dev/componentes' ? <Componentes /> : <App />}
  </StrictMode>,
)
