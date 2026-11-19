import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, act, useApi, Badge } from '../lib.jsx'
import NewProject from './NewProject.jsx'

export default function Avatar() {
  const nav = useNavigate()
  const prof = useApi('/settings/avatar_profile')
  const integ = useApi('/integrations')
  const scripts = useApi('/scripts')
  const [busy, setBusy] = useState(false)
  const [proj, setProj] = useState(null)
  const hg = integ.data?.find(i => i.key === 'heygen')
  const p = prof.data
  const upload = async e => {
    const f = e.target.files[0]; if (!f) return
    setBusy(true)
    const fd = new FormData(); fd.append('file', f)
    try { await act(() => api('/settings/reference/avatar', { method: 'POST', body: fd }), 'Avatar reference updated') ; prof.reload() } finally { setBusy(false) }
  }
  const approved = (scripts.data || []).filter(s => s.status === 'approved')
  return <div className="page">
    <div className="head"><div><h1>AI Avatar <em>Studio</em></h1><p>Your permanent presenter identity. Avatar videos are generated only from your own HeyGen Digital Twin and cloned voice. The studio never substitutes another presenter.</p></div></div>
    <div className="grid" style={{ gridTemplateColumns: '320px 1fr' }}>
      <div className="col">
        <div className="card">
          {p?._reference_video ? <video className="vid916" src={p._reference_video} controls /> : p?._reference_frame ? <img src={p._reference_frame} style={{ width: '100%', borderRadius: 12 }} /> : <div className="empty">No reference uploaded</div>}
          <label style={{ marginTop: 12 }}>Upload updated avatar reference</label>
          <input type="file" accept="video/*" disabled={busy} onChange={upload} />
          {busy && <div className="small muted">Uploading…</div>}
        </div>
      </div>
      <div className="col">
        <div className="card">
          <div className="row between"><h2>{p?.name}</h2><Badge s="approved">identity locked</Badge></div>
          <table><tbody>{p && Object.entries(p.observed || {}).map(([k, v]) => <tr key={k}><td className="dim" style={{ width: 160, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</td><td>{String(v)}</td></tr>)}</tbody></table>
          <div className="small dim" style={{ marginTop: 8 }}>{p?.identity_policy}</div>
        </div>
        <div className="card">
          <div className="row between"><h2>Generation provider: HeyGen</h2><Badge s={hg?.state} /></div>
          <p className="muted small">1) In HeyGen, create a Digital Twin (Instant Avatar) from footage like your reference video, then complete HeyGen's consent recording yourself. 2) Clone your voice in HeyGen. 3) Paste the API key, avatar_id and voice_id in <Link to="/integrations">Integrations</Link> and press Test.
            The script is sent as Roman Urdu. If pronunciation of a word is off, spell it phonetically in Script Studio.</p>
          {hg?.last_test && <div className={hg.last_test.ok ? 'note' : 'err'}>{hg.last_test.message}</div>}
          <div className="dim small" style={{ marginTop: 8 }}>No HeyGen yet? Choose "My own recording" when you create a project: record the approved script on your phone, upload it, and the studio edits it in your style.</div>
        </div>
        <div className="card">
          <h2>Create avatar video</h2>
          {approved.length === 0 ? <div className="muted">Approve a script in <Link to="/scripts">Script Studio</Link> first.</div> :
            <table><tbody>{approved.map(s => <tr key={s.id}><td><b>{s.title}</b><div className="small dim">{s.data?.word_count} words · ~{s.data?.estimated_duration_s}s</div></td>
              <td style={{ textAlign: 'right' }}><button className="btn primary sm" onClick={() => setProj(s)}>Create video</button></td></tr>)}</tbody></table>}
        </div>
      </div>
    </div>
    {proj && <NewProject preset={{ title: proj.title, topic: proj.title, script_id: String(proj.id), avatar_mode: hg?.state === 'connected' ? 'heygen' : 'own_recording' }} onClose={() => setProj(null)} onCreated={id => nav('/queue/' + id)} />}
  </div>
}
