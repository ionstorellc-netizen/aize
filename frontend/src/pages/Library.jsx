import { useState } from 'react'
import { api, act, useApi, Badge } from '../lib.jsx'

export default function Library() {
  const [kind, setKind] = useState('broll,image')
  const list = useApi('/assets?kind=' + kind, [kind])
  const integ = useApi('/integrations')
  const pexOk = ['connected', 'configured_untested'].includes(integ.data?.find(i => i.key === 'pexels')?.state)
  const [up, setUp] = useState({ kind: 'broll', tags: '', license: 'Own footage' })
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const upload = async e => {
    const files = [...e.target.files]; if (!files.length) return
    setBusy(true)
    try {
      for (const f of files) { const fd = new FormData(); fd.append('file', f); fd.append('kind', up.kind); fd.append('tags', up.tags); fd.append('license', up.license); await act(() => api('/assets', { method: 'POST', body: fd })) }
      list.reload()
    } finally { setBusy(false); e.target.value = '' }
  }
  const search = async () => setResults(await act(() => api('/stock/search?q=' + encodeURIComponent(q))))
  const imp = async it => { await act(() => api('/stock/import', { method: 'POST', body: { item: it } }), 'Imported into your library'); list.reload() }
  return <div className="page">
    <div className="head"><div><h1>B-Roll <em>Library</em></h1><p>Your own footage is used first. Tag clips with what they show (e.g. "yiwu, market, stalls") and the B-roll agent matches them to what you say. Pexels clips are licensed under the Pexels License.</p></div></div>
    <div className="grid g2" style={{ marginBottom: 16 }}>
      <div className="card"><h2>Upload media</h2>
        <div className="grid g3"><div><label>Type</label><select value={up.kind} onChange={e => setUp({ ...up, kind: e.target.value })}><option value="broll">B-roll video</option><option value="image">Image / screenshot</option><option value="music">Music (licensed)</option></select></div>
          <div><label>Tags</label><input value={up.tags} onChange={e => setUp({ ...up, tags: e.target.value })} placeholder="factory, packaging" /></div>
          <div><label>License / source</label><input value={up.license} onChange={e => setUp({ ...up, license: e.target.value })} /></div></div>
        <input type="file" multiple accept="video/*,image/*,audio/*" style={{ marginTop: 10 }} disabled={busy} onChange={upload} />
        {busy && <div className="small muted">Uploading…</div>}
      </div>
      <div className="card"><h2>Pexels stock search <Badge s={pexOk ? 'ok' : 'not_configured'}>{pexOk ? 'available' : 'add PEXELS_API_KEY'}</Badge></h2>
        <div className="row"><input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} placeholder="amazon warehouse, china factory…" style={{ flex: 1, width: 'auto' }} /><button className="btn" disabled={!pexOk || !q} onClick={search}>Search</button></div>
        {results.length > 0 && <div className="grid g4" style={{ marginTop: 10 }}>{results.map(r => <div key={r.id}><a href={r.url} target="_blank" className="small">{r.author}</a><div className="small dim">{r.width}x{r.height} · {r.duration}s</div><button className="btn sm" onClick={() => imp(r)}>Import</button></div>)}</div>}
      </div>
    </div>
    <div className="tabs">{[['broll,image', 'Footage & images'], ['music', 'Music'], ['avatar', 'Recordings'], ['render', 'Renders']].map(([k, l]) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{l}</button>)}</div>
    {(list.data || []).length === 0 ? <div className="empty">Nothing here yet.</div> :
      <div className="grid g4">{list.data.map(a => <div className="card" key={a.id} style={{ padding: 10 }}>
        {a.kind === 'image' ? <img src={a.url} style={{ width: '100%', borderRadius: 8, aspectRatio: '16/10', objectFit: 'cover' }} /> :
          a.kind === 'music' ? <audio src={a.url} controls style={{ width: '100%' }} /> :
            <video src={a.url} muted preload="metadata" style={{ width: '100%', aspectRatio: '16/10', objectFit: 'cover' }} onMouseOver={e => e.target.play()} onMouseOut={e => e.target.pause()} />}
        <input defaultValue={a.name} style={{ marginTop: 6 }} onBlur={e => e.target.value !== a.name && api('/assets/' + a.id, { method: 'PATCH', body: { name: e.target.value } })} />
        <input defaultValue={(a.tags || []).join(', ')} placeholder="tags" style={{ marginTop: 6 }} onBlur={e => api('/assets/' + a.id, { method: 'PATCH', body: { tags: e.target.value.split(',').map(t => t.trim()).filter(Boolean) } })} />
        <div className="row between small" style={{ marginTop: 6 }}><span className="dim">{a.source}{a.duration ? ` · ${a.duration.toFixed(1)}s` : ''}</span>
          {a.source_url ? <a href={a.source_url} target="_blank">source</a> : null}
          <button className="btn sm danger" onClick={async () => { await api('/assets/' + a.id, { method: 'DELETE' }); list.reload() }}>Delete</button></div>
        <div className="small dim">{a.license}</div>
      </div>)}</div>}
  </div>
}
