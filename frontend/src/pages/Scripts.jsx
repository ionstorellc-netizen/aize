import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api, act, useApi, Badge, useJob, Modal, Err } from '../lib.jsx'
import NewProject from './NewProject.jsx'

const WPS = 2.6
const blankScene = () => ({ start_s: 0, end_s: 0, purpose: 'value', spoken: '', broll_queries: [], visual_direction: '', sfx: '' })

export default function Scripts() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const list = useApi('/scripts')
  const integ = useApi('/integrations')
  const claudeOk = ['connected', 'configured_untested'].includes(integ.data?.find(i => i.key === 'anthropic')?.state)
  const [sel, setSel] = useState(null)
  const [draft, setDraft] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [genOpen, setGenOpen] = useState(sp.get('new') === '1')
  const [manualOpen, setManualOpen] = useState(false)
  const [gen, setGen] = useState({ topic: '', notes: '' })
  const [man, setMan] = useState({ title: '', text: '' })
  const [proj, setProj] = useState(false)
  const job = useJob(() => list.reload())
  useEffect(() => { if (sp.get('job')) job.start(+sp.get('job')) }, [])
  useEffect(() => { if (list.data && !sel && list.data.length) pick(list.data[0]) }, [list.data])
  const pick = s => { setSel(s.id); setDraft(JSON.parse(JSON.stringify(s))); setDirty(false) }
  const cur = list.data?.find(s => s.id === sel)
  const d = draft?.data
  const upd = fn => { setDraft(x => { const y = JSON.parse(JSON.stringify(x)); fn(y.data, y); return y }); setDirty(true) }
  const words = d ? (d.scenes || []).map(s => s.spoken).join(' ').split(/\s+/).filter(Boolean).length : 0
  const save = async () => { await act(() => api('/scripts/' + sel, { method: 'PUT', body: { title: draft.title, data: draft.data } }), 'Saved (status reset to draft)'); setDirty(false); list.reload() }
  const approve = async () => { if (dirty) await save(); await act(() => api(`/scripts/${sel}/approve`, { method: 'POST' }), 'Script approved'); list.reload() }
  const generate = async () => { const r = await act(() => api('/scripts/generate', { method: 'POST', body: gen }), 'Writing script…'); setGenOpen(false); job.start(r.job_id) }
  const manual = async () => { const r = await act(() => api('/scripts', { method: 'POST', body: man }), 'Script saved'); setManualOpen(false); await list.reload(); setSel(null) }
  return <div className="page">
    <div className="head"><div><h1>Script <em>Studio</em></h1><p>30–50 second Roman Urdu scripts: hook, problem, value, payoff, CTA. Edit every line, then approve before production.</p></div>
      <div className="row"><button className="btn" onClick={() => setManualOpen(true)}>Write manually</button>
        <button className="btn primary" disabled={!claudeOk || job.running} title={claudeOk ? '' : 'Add your Anthropic key in Integrations'} onClick={() => setGenOpen(true)}>{job.running ? 'Writing…' : 'Generate script'}</button></div></div>
    {!claudeOk && <div className="note" style={{ marginBottom: 14 }}>Claude is not connected, so scripts can't be generated yet. You can still write or paste scripts manually.</div>}
    <div className="grid" style={{ gridTemplateColumns: '280px 1fr' }}>
      <div className="card" style={{ padding: 8, alignSelf: 'start' }}>
        {(list.data || []).length === 0 && <div className="empty">No scripts yet.</div>}
        {(list.data || []).map(s => <div key={s.id} onClick={() => pick(s)} style={{ padding: 10, borderRadius: 10, cursor: 'pointer', background: sel === s.id ? 'var(--panel2)' : '' }}>
          <div style={{ fontWeight: 600 }}>{s.title}</div><div className="row small dim">#{s.id} <Badge s={s.status} /> {s.data?.estimated_duration_s}s · {s.source}</div></div>)}
      </div>
      {d ? <div className="col">
        <div className="card">
          <div className="row between">
            <input style={{ fontSize: 18, fontWeight: 700, maxWidth: 560 }} value={draft.title} onChange={e => { setDraft({ ...draft, title: e.target.value }); setDirty(true) }} />
            <div className="row"><Badge s={cur?.status} /><span className={words / WPS < 30 || words / WPS > 50 ? 'badge warn' : 'badge ok'}>{words} words · ~{(words / WPS).toFixed(0)}s spoken</span>
              <button className="btn" disabled={!dirty} onClick={save}>Save</button>
              <button className="btn green" onClick={approve}>Approve</button>
              <button className="btn primary" onClick={() => setProj(true)}>Produce video</button></div>
          </div>
          <div className="grid g3" style={{ marginTop: 14 }}>
            <div><label>On-screen hook title</label><input value={d.hook_title || ''} onChange={e => upd(x => x.hook_title = e.target.value)} /></div>
            <div><label>Hook second line (gold italic)</label><input value={d.hook_subtitle || ''} onChange={e => upd(x => x.hook_subtitle = e.target.value)} /></div>
            <div><label>CTA comment keyword</label><input value={d.cta_keyword || ''} onChange={e => upd(x => x.cta_keyword = e.target.value)} /></div>
          </div>
          <div className="grid g2" style={{ marginTop: 10 }}>
            <div><label>CTA line (on screen)</label><input value={d.cta || ''} onChange={e => upd(x => x.cta = e.target.value)} /></div>
            <div><label>Keyword callouts (comma separated, as spoken)</label><input value={(d.keywords || []).join(', ')} onChange={e => upd(x => x.keywords = e.target.value.split(',').map(s => s.trim()).filter(Boolean))} /></div>
          </div>
          {d.hook_variations?.length > 0 && <div style={{ marginTop: 12 }}><label>Hook variations (click to use as first line)</label>
            {d.hook_variations.map((h, i) => <div key={i} className="row small" style={{ padding: '3px 0' }}><button className="btn sm" onClick={() => upd(x => { x.scenes[0].spoken = h })}>Use</button><span>{h}</span></div>)}</div>}
        </div>
        {(d.scenes || []).map((sc, i) => <div className="card" key={i}>
          <div className="row between" style={{ marginBottom: 8 }}>
            <div className="row"><Badge>{sc.purpose}</Badge><span className="dim small">{sc.start_s}–{sc.end_s}s planned · {sc.spoken.split(/\s+/).filter(Boolean).length} words</span></div>
            <div className="row"><select style={{ width: 110 }} value={sc.purpose} onChange={e => upd(x => x.scenes[i].purpose = e.target.value)}>{['hook', 'problem', 'value', 'payoff', 'cta'].map(p => <option key={p}>{p}</option>)}</select>
              <button className="btn sm danger" onClick={() => upd(x => x.scenes.splice(i, 1))}>Remove</button></div></div>
          <label>Spoken (Roman Urdu) — this is also the subtitle transcript</label>
          <textarea value={sc.spoken} onChange={e => upd(x => x.scenes[i].spoken = e.target.value)} style={{ fontSize: 15 }} />
          <div className="grid g3" style={{ marginTop: 8 }}>
            <div><label>B-roll queries</label><input value={(sc.broll_queries || []).join(', ')} onChange={e => upd(x => x.scenes[i].broll_queries = e.target.value.split(',').map(s => s.trim()).filter(Boolean))} /></div>
            <div><label>Visual direction</label><input value={sc.visual_direction || ''} onChange={e => upd(x => x.scenes[i].visual_direction = e.target.value)} /></div>
            <div><label>Sound effect</label><input value={sc.sfx || ''} onChange={e => upd(x => x.scenes[i].sfx = e.target.value)} /></div>
          </div></div>)}
        <button className="btn" onClick={() => upd(x => (x.scenes = x.scenes || []).push(blankScene()))}>+ Add scene</button>
        {d.fact_check_notes?.length > 0 && <div className="note"><b>Verify before publishing:</b><ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{d.fact_check_notes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>}
      </div> : <div className="empty">Select or create a script.</div>}
    </div>
    {genOpen && <Modal title="Generate script with Claude" onClose={() => setGenOpen(false)}>
      <div className="field"><label>Topic</label><textarea value={gen.topic} onChange={e => setGen({ ...gen, topic: e.target.value })} placeholder="e.g. Yiwu market mein pehli dafa sourcing karne walon ki 3 galtiyan" /></div>
      <div className="field"><label>Extra notes (facts to include, angle, offer)</label><textarea value={gen.notes} onChange={e => setGen({ ...gen, notes: e.target.value })} /></div>
      <div className="dim small" style={{ marginBottom: 10 }}>Tip: generate from an approved idea in Content Ideas to include research context.</div>
      <button className="btn primary" disabled={!gen.topic} onClick={generate}>Generate</button></Modal>}
    {manualOpen && <Modal title="Write script manually" onClose={() => setManualOpen(false)}>
      <div className="field"><label>Title</label><input value={man.title} onChange={e => setMan({ ...man, title: e.target.value })} /></div>
      <div className="field"><label>Spoken script in Roman Urdu (each sentence becomes a scene)</label><textarea rows={10} value={man.text} onChange={e => setMan({ ...man, text: e.target.value })} /></div>
      <div className="dim small" style={{ marginBottom: 10 }}>{man.text.split(/\s+/).filter(Boolean).length} words · ~{(man.text.split(/\s+/).filter(Boolean).length / WPS).toFixed(0)}s</div>
      <button className="btn primary" disabled={!man.title || !man.text} onClick={manual}>Save script</button></Modal>}
    {proj && <NewProject preset={{ title: draft.title, topic: draft.title, script_id: String(sel) }} onClose={() => setProj(false)} onCreated={id => nav('/queue/' + id)} />}
  </div>
}
