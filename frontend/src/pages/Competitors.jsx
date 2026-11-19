import { useState } from 'react'
import { api, act, useApi, Badge, fmtN, Modal } from '../lib.jsx'

export default function Competitors() {
  const list = useApi('/competitors')
  const [open, setOpen] = useState(null)
  const [add, setAdd] = useState(false)
  const [ig, setIg] = useState('')
  const [f, setF] = useState({ platform: 'TikTok', name: '', url: '', followers: '', top_video_url: '', top_video_views: '', hook: '', format: '', notes: '' })
  const save = async () => {
    await act(() => api('/competitors', { method: 'POST', body: { ...f, followers: f.followers ? +f.followers : null, top_video_views: f.top_video_views ? +f.top_video_views : null } }), 'Competitor added (unverified)')
    setAdd(false); list.reload()
  }
  const addIg = async () => { await act(() => api('/competitors/instagram/' + encodeURIComponent(ig), { method: 'POST' }), 'Instagram account added (verified)'); setIg(''); list.reload() }
  return <div className="page">
    <div className="head"><div><h1>Competitor <em>Intelligence</em></h1><p>YouTube channels are discovered automatically by Viral Research with verified API metrics. Instagram accounts are looked up through the Graph API. TikTok accounts are added manually and stay labelled unverified.</p></div>
      <div className="row"><input style={{ width: 200 }} placeholder="instagram username" value={ig} onChange={e => setIg(e.target.value)} /><button className="btn" disabled={!ig} onClick={addIg}>Add Instagram</button>
        <button className="btn primary" onClick={() => setAdd(true)}>Add manually</button></div></div>
    <div className="card">
      {(list.data || []).length === 0 ? <div className="empty">No competitors yet. Run Viral Research or add accounts manually.</div> :
        <table><thead><tr><th>Account</th><th>Platform</th><th>Followers</th><th>Top videos</th><th>Data</th><th></th></tr></thead>
          <tbody>{list.data.map(c => <tr key={c.id}>
            <td><a href={c.url} target="_blank"><b>{c.name}</b></a><div className="small dim">{c.data?.handle || ''} {c.data?.country || ''}</div></td>
            <td>{c.platform}</td><td>{fmtN(c.followers)}{c.data?.followers_note && <div className="small dim">{c.data.followers_note}</div>}</td>
            <td style={{ maxWidth: 420 }}>{(c.data?.top_videos || c.data?.videos || []).slice(0, 2).map((v, i) => <div key={i} className="small"><a href={v.url} target="_blank">{v.title || v.url}</a> <span className="dim">{fmtN(v.views)} views · {fmtN(v.likes)} likes · {v.published_at?.slice(0, 10) || ''}</span></div>)}
              {(c.data?.top_videos?.length > 2) && <button className="btn sm" onClick={() => setOpen(c)}>All {c.data.top_videos.length}</button>}</td>
            <td><Badge s={c.verification} /><div className="small dim">{c.source.replace('_', ' ')}</div></td>
            <td><button className="btn sm danger" onClick={async () => { await api('/competitors/' + c.id, { method: 'DELETE' }); list.reload() }}>Remove</button></td></tr>)}</tbody></table>}
    </div>
    {open && <Modal title={open.name} onClose={() => setOpen(null)}>
      <table><tbody>{open.data.top_videos.map((v, i) => <tr key={i}><td><a href={v.url} target="_blank">{v.title}</a></td><td>{fmtN(v.views)}</td><td>{fmtN(v.likes)}</td><td>{fmtN(v.comments)}</td><td className="small">{v.published_at?.slice(0, 10)}</td></tr>)}</tbody></table>
    </Modal>}
    {add && <Modal title="Add competitor (user-entered, unverified)" onClose={() => setAdd(false)}>
      <div className="grid g2">
        <div className="field"><label>Platform</label><select value={f.platform} onChange={e => setF({ ...f, platform: e.target.value })}>{['TikTok', 'Instagram', 'YouTube', 'Facebook'].map(p => <option key={p}>{p}</option>)}</select></div>
        <div className="field"><label>Account name</label><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div className="field"><label>Profile link</label><input value={f.url} onChange={e => setF({ ...f, url: e.target.value })} /></div>
        <div className="field"><label>Followers (as shown on profile)</label><input type="number" value={f.followers} onChange={e => setF({ ...f, followers: e.target.value })} /></div>
        <div className="field"><label>Most-viewed video link</label><input value={f.top_video_url} onChange={e => setF({ ...f, top_video_url: e.target.value })} /></div>
        <div className="field"><label>Its views</label><input type="number" value={f.top_video_views} onChange={e => setF({ ...f, top_video_views: e.target.value })} /></div>
        <div className="field"><label>Hook used</label><input value={f.hook} onChange={e => setF({ ...f, hook: e.target.value })} /></div>
        <div className="field"><label>Content format</label><input value={f.format} onChange={e => setF({ ...f, format: e.target.value })} /></div>
      </div>
      <div className="field"><label>Notes</label><textarea value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} /></div>
      <button className="btn primary" disabled={!f.name || !f.url} onClick={save}>Save</button>
    </Modal>}
  </div>
}
