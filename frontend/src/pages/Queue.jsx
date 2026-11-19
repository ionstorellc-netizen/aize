import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api, act, useApi, Badge, Stages, ago } from '../lib.jsx'

export default function Queue() {
  const { pid } = useParams()
  const nav = useNavigate()
  const list = useApi('/projects', [], 4000)
  const p = useApi(pid ? '/projects/' + pid : null, [pid], 2500)
  const [busy, setBusy] = useState(false)
  const P = p.data
  const approve = async st => { await act(() => api(`/projects/${pid}/stages/${st}/approve`, { method: 'POST' }), 'Approved, continuing'); p.reload() }
  const retry = async st => { await act(() => api(`/projects/${pid}/stages/${st}/retry`, { method: 'POST' }), 'Restarted from this stage'); p.reload() }
  const upload = async e => {
    const f = e.target.files[0]; if (!f) return
    setBusy(true); const fd = new FormData(); fd.append('file', f)
    try { await act(() => api(`/projects/${pid}/recording`, { method: 'POST', body: fd }), 'Recording uploaded'); p.reload() } finally { setBusy(false) }
  }
  return <div className="page" style={{ maxWidth: 'none' }}>
    <div className="head"><div><h1>Production <em>Queue</em></h1><p>Every video is its own project with 12 saved stages. Failed stages show the reason and can be retried without redoing finished work.</p></div></div>
    <div className="grid" style={{ gridTemplateColumns: '360px 1fr', alignItems: 'start' }}>
      <div className="card" style={{ padding: 8 }}>
        {(list.data || []).length === 0 && <div className="empty">No projects yet.</div>}
        {(list.data || []).map(x => <div key={x.id} onClick={() => nav('/queue/' + x.id)} style={{ padding: 10, borderRadius: 10, cursor: 'pointer', background: +pid === x.id ? 'var(--panel2)' : '' }}>
          <div className="row between"><b>{x.title}</b><Badge s={x.status} /></div>
          <div className="small dim" style={{ margin: '2px 0 8px' }}>#{x.id} · {x.avatar_mode === 'heygen' ? 'AI avatar' : 'own recording'} · {ago(x.updated_at)}</div>
          <Stages stages={x.stages} /></div>)}
      </div>
      {!P ? <div className="empty">Select a project.</div> : <div className="col">
        <div className="card">
          <div className="row between"><div><h2 style={{ fontSize: 20 }}>{P.title}</h2><div className="muted small">{P.topic}</div></div>
            <div className="row"><Badge s={P.status} /><span className="small dim">API cost ${P.cost_usd.toFixed(3)}</span>
              {P.has_edl && <Link className="btn" to={'/editor/' + P.id}>Open in editor</Link>}
              <button className="btn" onClick={async () => { const r = await api(`/projects/${P.id}/duplicate`, { method: 'POST' }); nav('/queue/' + r.id) }}>Duplicate</button>
              <button className="btn danger" onClick={async () => { if (confirm('Delete this project and its files?')) { await api('/projects/' + P.id, { method: 'DELETE' }); nav('/queue') } }}>Delete</button></div></div>
          {P.avatar_mode === 'own_recording' && <div className="row" style={{ marginTop: 12 }}><label style={{ margin: 0 }}>Recording:</label>
            <span className="small">{P.recording_asset_id ? 'uploaded ✓' : 'not uploaded'}</span><input type="file" accept="video/*" style={{ width: 280 }} disabled={busy} onChange={upload} />{busy && <span className="small muted">Uploading…</span>}</div>}
        </div>
        <div className="card" style={{ padding: 0 }}>
          <table><thead><tr><th style={{ width: 30 }}>#</th><th>Stage</th><th>Status</th><th>Result</th><th></th></tr></thead><tbody>
            {P.stages.map((s, i) => <tr key={s.name}><td className="dim">{i + 1}</td><td><b>{s.label}</b>{s.attempts > 1 && <div className="small dim">{s.attempts} attempts</div>}</td>
              <td><Badge s={s.status} /></td><td className="small" style={{ maxWidth: 560 }}>{s.message}
                {s.name === 'script_approval' && P.script_id && <div><Link to="/scripts">Open script #{P.script_id} in Script Studio</Link></div>}</td>
              <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                {s.status === 'requires_approval' && !(s.name === 'avatar_generation' && !P.recording_asset_id && P.avatar_mode === 'own_recording') && <button className="btn sm green" onClick={() => approve(s.name)}>{s.name === 'quality_control' ? 'Override & approve' : 'Approve'}</button>}{' '}
                {['failed', 'completed', 'skipped', 'requires_approval'].includes(s.status) && <button className="btn sm" onClick={() => retry(s.name)}>{s.status === 'failed' ? 'Retry' : 'Re-run from here'}</button>}</td></tr>)}
          </tbody></table>
        </div>
        <div className="grid g2">
          <div className="card"><h2>Preview</h2>
            {P.master ? <video className="vid916" style={{ maxHeight: 560 }} src={P.master + '?t=' + P.updated_at} controls /> : P.preview ? <video className="vid916" style={{ maxHeight: 560 }} src={P.preview} controls /> : <div className="empty">Appears after the master render.</div>}
            {P.export && <div className="row" style={{ marginTop: 10 }}><a className="btn primary" href={P.export.mp4} download>Download MP4</a><a className="btn" href={P.export.srt} download>Subtitles .srt</a><a className="btn" href={P.export.ass} download>Styled .ass</a></div>}
          </div>
          <div className="col">
            {P.qc && <div className="card"><div className="row between"><h2>Quality control</h2><Badge s={P.qc.passed ? 'pass' : 'fail'}>{P.qc.passed ? 'passed' : 'critical issues'}</Badge></div>
              <table><tbody>{P.qc.checks.map(c => <tr key={c.check}><td><b className="small">{c.check}</b>{c.critical && <span className="dim small"> · critical</span>}</td><td><Badge s={c.status} /></td><td className="small muted">{c.detail}</td></tr>)}</tbody></table></div>}
            <div className="card"><h2>Agent log</h2>{(P.jobs || []).map(j => <div key={j.id} style={{ marginBottom: 10 }}><div className="row small"><Badge s={j.status} /> job #{j.id} {j.kind} {j.error && <span style={{ color: 'var(--bad)' }}>{j.error}</span>}</div>
              {j.log && <div className="pre" style={{ marginTop: 6 }}>{j.log}</div>}</div>)}</div>
          </div>
        </div>
      </div>}
    </div>
  </div>
}
