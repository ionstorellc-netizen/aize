import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import './styles.css'
import { Toaster } from './lib.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Research from './pages/Research.jsx'
import Competitors from './pages/Competitors.jsx'
import Ideas from './pages/Ideas.jsx'
import Scripts from './pages/Scripts.jsx'
import Avatar from './pages/Avatar.jsx'
import Editor from './pages/Editor.jsx'
import Library from './pages/Library.jsx'
import Templates from './pages/Templates.jsx'
import Queue from './pages/Queue.jsx'
import Completed from './pages/Completed.jsx'
import Analytics from './pages/Analytics.jsx'
import Integrations from './pages/Integrations.jsx'
import Settings from './pages/Settings.jsx'
import NewProject from './pages/NewProject.jsx'

const NAV = [
  ['/', 'Dashboard'], ['/research', 'Viral Research'], ['/competitors', 'Competitor Intelligence'], ['/ideas', 'Content Ideas'],
  ['/scripts', 'Script Studio'], ['/avatar', 'AI Avatar Studio'], ['/editor', 'Video Editor'], ['/library', 'B-Roll Library'],
  ['/templates', 'Editing Templates'], ['/queue', 'Production Queue'], ['/completed', 'Completed Videos'],
  ['/analytics', 'Analytics'], ['/integrations', 'Integrations'], ['/settings', 'Settings'],
]

function Shell() {
  const [newOpen, setNewOpen] = useState(false)
  const nav = useNavigate()
  return <div className="app">
    <aside className="side">
      <div className="brand"><b>E-com <i>Studio</i></b><span>AI video production</span></div>
      <button className="btn primary" style={{ width: '100%', justifyContent: 'center', marginBottom: 16 }} onClick={() => setNewOpen(true)}>+ New video project</button>
      <nav className="nav">{NAV.map(([to, l], i) => <NavLink key={to} to={to} end={to === '/'}><span className="n">{i + 1}</span>{l}</NavLink>)}</nav>
    </aside>
    <main className="main">
      <Routes>
        <Route path="/" element={<Dashboard onNew={() => setNewOpen(true)} />} />
        <Route path="/research" element={<Research />} />
        <Route path="/competitors" element={<Competitors />} />
        <Route path="/ideas" element={<Ideas />} />
        <Route path="/scripts" element={<Scripts />} />
        <Route path="/avatar" element={<Avatar />} />
        <Route path="/editor" element={<Editor />} />
        <Route path="/editor/:pid" element={<Editor />} />
        <Route path="/library" element={<Library />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/queue/:pid" element={<Queue />} />
        <Route path="/completed" element={<Completed />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </main>
    {newOpen && <NewProject onClose={() => setNewOpen(false)} onCreated={id => { setNewOpen(false); nav('/queue/' + id) }} />}
    <Toaster />
  </div>
}

createRoot(document.getElementById('root')).render(<BrowserRouter><Shell /></BrowserRouter>)
