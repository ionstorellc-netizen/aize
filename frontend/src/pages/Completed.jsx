import { useNavigate } from 'react-router-dom'
import { api, useApi, ago } from '../lib.jsx'

export default function Completed() {
  const nav = useNavigate()
  const list = useApi('/projects')
  const done = (list.data || []).filter(p => p.export)
  return <div className="page">
    <div className="head"><div><h1>Completed <em>Videos</em></h1><p>Final 1080×1920 H.264/AAC MP4s, no watermark, with matching subtitle files.</p></div></div>
    {done.length === 0 ? <div className="empty">No exported videos yet.</div> :
      <div className="grid g4">{done.map(p => <div className="card col" key={p.id} style={{ padding: 12 }}>
        <video className="vid916" src={p.export.mp4} poster={p.export.thumb} controls preload="none" />
        <b>{p.title}</b><div className="small dim">{p.category} · {ago(p.updated_at)}</div>
        <div className="row"><a className="btn sm primary" href={p.export.mp4} download>MP4</a><a className="btn sm" href={p.export.srt} download>SRT</a><a className="btn sm" href={p.export.ass} download>ASS</a></div>
        <div className="row"><button className="btn sm" onClick={() => nav('/editor/' + p.id)}>Re-edit</button>
          <button className="btn sm" onClick={async () => { const r = await api(`/projects/${p.id}/duplicate`, { method: 'POST' }); nav('/queue/' + r.id) }}>Duplicate</button>
          <button className="btn sm" onClick={() => nav('/queue/' + p.id)}>Details</button></div>
      </div>)}</div>}
  </div>
}
