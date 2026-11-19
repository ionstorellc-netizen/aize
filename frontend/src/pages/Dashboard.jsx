import { Link, useNavigate } from 'react-router-dom'
import { useApi, Badge, Stages, fmtN, ago, Err } from '../lib.jsx'

export default function Dashboard({ onNew }) {
  const { data: d, error } = useApi('/dashboard', [], 5000)
  const nav = useNavigate()
  if (error) return <div className="page"><Err e={error} /></div>
  if (!d) return <div className="page muted">Loading…</div>
  const t = d.totals
  const lastWithEdit = d.recent.find(p => p.stages.find(s => s.name === 'video_editing' && s.status === 'completed'))
  return <div className="page">
    <div className="hero">
      <div>
        <div className="dim small" style={{ letterSpacing: '.14em', textTransform: 'uppercase' }}>Premium AI E-commerce Video Studio</div>
        <h1 style={{ marginTop: 8 }}>Research, script, film and edit. <em>One click.</em></h1>
        <p className="muted" style={{ margin: '8px 0 0' }}>Every project inherits your avatar, your editing style and your export settings.</p>
      </div>
      <button className="btn primary big" onClick={onNew}>START NEW VIDEO PROJECT</button>
    </div>

    <div className="row" style={{ margin: '16px 0 22px' }}>
      <button className="btn" onClick={() => nav('/research?run=1')}>Start viral research</button>
      <button className="btn" onClick={() => nav('/scripts?new=1')}>Generate script</button>
      <button className="btn" onClick={() => nav('/avatar')}>Create avatar video</button>
      <button className="btn" onClick={() => nav(lastWithEdit ? '/editor/' + lastWithEdit.id : '/editor')}>Open video editor</button>
    </div>

    <div className="grid g6" style={{ marginBottom: 16 }}>
      {[['Videos produced', t.videos_produced], ['Processing', t.processing], ['Awaiting approval', t.waiting],
        ['Failed jobs', t.failed_jobs], ['Saved scripts', t.saved_scripts], ['API spend', '$' + t.cost_usd.toFixed(2)]].map(([l, v]) =>
        <div className="card kpi" key={l}><div className="l">{l}</div><div className="v">{v}</div></div>)}
    </div>

    <div className="grid g3">
      <div className="card" style={{ gridColumn: 'span 2' }}>
        <div className="row between"><h2>Recent video projects</h2><Link to="/queue">Production queue →</Link></div>
        {d.recent.length === 0 ? <div className="empty">No projects yet. Start your first video.</div> :
          <table><tbody>{d.recent.map(p => <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => nav('/queue/' + p.id)}>
            <td style={{ width: 70 }}>{p.export?.thumb ? <img src={p.export.thumb} style={{ width: 44, borderRadius: 6 }} /> : <div style={{ width: 44, height: 78, background: 'var(--panel2)', borderRadius: 6 }} />}</td>
            <td><b>{p.title}</b><div className="dim small">{p.category || 'No category'} · {ago(p.updated_at)}</div><div style={{ marginTop: 8, maxWidth: 360 }}><Stages stages={p.stages} /></div></td>
            <td style={{ textAlign: 'right' }}><Badge s={p.status} /></td></tr>)}</tbody></table>}
      </div>
      <div className="col">
        <div className="card">
          <div className="row between"><h2>API integrations</h2><Link to="/integrations">Manage →</Link></div>
          {d.integrations.map(i => <div key={i.key} className="row between" style={{ padding: '5px 0' }}><span>{i.label}</span><Badge s={i.state} /></div>)}
        </div>
        <div className="card">
          <h2>Trending topics</h2>
          {d.trending.length ? <ul style={{ paddingLeft: 18, margin: 0 }}>{d.trending.slice(0, 6).map((x, i) => <li key={i}>{x}</li>)}</ul>
            : <div className="muted small">No research yet. Trending topics come from real YouTube data once the YouTube API key is added.</div>}
          {d.trending_source && <div className="dim small" style={{ marginTop: 8 }}>Source: {d.trending_source}</div>}
        </div>
        <div className="card">
          <div className="row between"><h2>Recent competitor discoveries</h2><Link to="/competitors">All →</Link></div>
          {d.competitors.length ? d.competitors.map((c, i) => <div key={i} className="row between" style={{ padding: '4px 0' }}>
            <a href={c.url} target="_blank">{c.name}</a><span className="small muted">{fmtN(c.followers)} <Badge s={c.verification} /></span></div>)
            : <div className="muted small">None yet.</div>}
        </div>
      </div>
    </div>
  </div>
}
