import { useState } from 'react'
import { api, act, Modal, useApi, CATEGORIES } from '../lib.jsx'

export default function NewProject({ onClose, onCreated, preset = {} }) {
  const ideas = useApi('/ideas?status=approved')
  const scripts = useApi('/scripts')
  const runs = useApi('/research')
  const integ = useApi('/integrations')
  const heygenOk = integ.data?.find(i => i.key === 'heygen')?.state === 'connected'
  const [f, setF] = useState({ title: '', topic: '', category: 'Amazon', avatar_mode: heygenOk ? 'heygen' : 'own_recording',
    idea_id: '', script_id: '', research_run_id: '', ...preset })
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  const submit = async () => {
    setBusy(true)
    try {
      const body = { ...f, idea_id: f.idea_id ? +f.idea_id : null, script_id: f.script_id ? +f.script_id : null,
        research_run_id: f.research_run_id ? +f.research_run_id : null, title: f.title || f.topic || 'Untitled video', auto_start: !file }
      const { id } = await act(() => api('/projects', { method: 'POST', body }), 'Project created')
      if (file) {
        const fd = new FormData(); fd.append('file', file)
        await act(() => api(`/projects/${id}/recording`, { method: 'POST', body: fd }), 'Recording uploaded')
        await api(`/projects/${id}/start`, { method: 'POST' })
      }
      onCreated(id)
    } finally { setBusy(false) }
  }
  return <Modal title="Start new video project" onClose={onClose}>
    <div className="field"><label>Title</label><input value={f.title} onChange={e => set('title', e.target.value)} placeholder="e.g. Yiwu market: 3 mistakes new sellers make" /></div>
    <div className="field"><label>Topic or request (leave empty and pick an approved idea, or run research first)</label>
      <textarea value={f.topic} onChange={e => set('topic', e.target.value)} placeholder="What should this video teach?" /></div>
    <div className="grid g2">
      <div className="field"><label>Category</label><select value={f.category} onChange={e => set('category', e.target.value)}>{CATEGORIES.map(c => <option key={c}>{c}</option>)}</select></div>
      <div className="field"><label>Presenter source</label><select value={f.avatar_mode} onChange={e => set('avatar_mode', e.target.value)}>
        <option value="heygen">AI avatar (HeyGen Digital Twin){heygenOk ? '' : ' — not connected'}</option>
        <option value="own_recording">My own recording (upload a take)</option></select></div>
    </div>
    <div className="grid g2">
      <div className="field"><label>Approved idea (optional)</label><select value={f.idea_id} onChange={e => set('idea_id', e.target.value)}>
        <option value="">—</option>{(ideas.data || []).map(i => <option key={i.id} value={i.id}>{i.title}</option>)}</select></div>
      <div className="field"><label>Existing script (optional)</label><select value={f.script_id} onChange={e => set('script_id', e.target.value)}>
        <option value="">— generate a new one</option>{(scripts.data || []).map(s => <option key={s.id} value={s.id}>#{s.id} {s.title} ({s.status})</option>)}</select></div>
    </div>
    <div className="field"><label>Research run (optional)</label><select value={f.research_run_id} onChange={e => set('research_run_id', e.target.value)}>
      <option value="">— run research automatically if YouTube is connected</option>{(runs.data || []).filter(r => r.status === 'done').map(r => <option key={r.id} value={r.id}>#{r.id} {r.query || r.categories.join(', ')}</option>)}</select></div>
    {f.avatar_mode === 'own_recording' && <div className="field"><label>Recording (optional now, you can upload later)</label>
      <input type="file" accept="video/*" onChange={e => setFile(e.target.files[0])} /></div>}
    <div className="row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={busy || !(f.title || f.topic || f.idea_id)} onClick={submit}>{busy ? 'Working…' : 'Create and start'}</button>
    </div>
  </Modal>
}
