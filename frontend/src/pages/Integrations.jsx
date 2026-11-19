import { useState } from 'react'
import { api, act, useApi, Badge, ago } from '../lib.jsx'

const DOCS = {
  anthropic: ['https://console.anthropic.com/settings/keys', 'Create an API key in the Claude Console.'],
  youtube: ['https://console.cloud.google.com/apis/library/youtube.googleapis.com', 'Enable "YouTube Data API v3" in a Google Cloud project, then create an API key under Credentials.'],
  pexels: ['https://www.pexels.com/api/', 'Free key (Pexels has paused new keys; use Pixabay instead).'],
  pixabay: ['https://pixabay.com/api/docs/', 'Free key, instant: sign in at pixabay.com, open the API docs page, and copy your key (it is shown on that page once you are signed in). Used for B-roll when Pexels has no key.'],
  heygen: ['https://docs.heygen.com/', 'API key: HeyGen > Settings > API. avatar_id: your Digital Twin (Avatars > your twin). voice_id: your cloned voice.'],
  instagram: ['https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery', 'Needs an Instagram Business/Creator account linked to a Facebook Page and a long-lived token. INSTAGRAM_BUSINESS_ID is your IG user id.'],
}

function Provider({ p, reload }) {
  const [vals, setVals] = useState({})
  const [busy, setBusy] = useState(false)
  const save = async () => { await act(() => api('/integrations/' + p.key, { method: 'PUT', body: { values: vals } }), 'Saved on the server (encrypted)'); setVals({}); reload() }
  const test = async () => { setBusy(true); try { const r = await api(`/integrations/${p.key}/test`, { method: 'POST' }); act(async () => { if (!r.ok) throw new Error(r.message) }, r.message).catch(() => {}); reload() } finally { setBusy(false) } }
  return <div className="card col">
    <div className="row between"><h2 style={{ margin: 0 }}>{p.label}</h2><Badge s={p.state} /></div>
    <div className="small muted">{p.use}</div>
    <div className="small dim">{p.pricing}</div>
    {p.fields.map(f => <div key={f.name}><label>{f.name} <span className="dim">({f.status === 'env' ? 'set in environment' : f.status})</span></label>
      <input type={f.secret ? 'password' : 'text'} autoComplete="off" placeholder={f.value || (f.secret ? 'paste key' : '')} value={vals[f.name] ?? ''} disabled={f.status === 'env'} onChange={e => setVals({ ...vals, [f.name]: e.target.value })} /></div>)}
    {p.fields.length > 0 && <div className="row"><button className="btn" disabled={!Object.keys(vals).length} onClick={save}>Save</button><button className="btn green" disabled={busy || p.state === 'not_configured'} onClick={test}>{busy ? 'Testing…' : 'Test connection'}</button>
      {DOCS[p.key] && <a className="small" href={DOCS[p.key][0]} target="_blank">Get credentials ↗</a>}</div>}
    {DOCS[p.key] && <div className="small dim">{DOCS[p.key][1]}</div>}
    {p.last_test && <div className={p.last_test.ok ? 'note' : 'err'} style={{ fontSize: 12 }}>{p.last_test.ok ? 'Last test passed' : 'Last test failed'} {ago(p.last_test.at)}: {p.last_test.message}</div>}
    {p.usage && p.usage.calls !== undefined && <div className="small dim">Usage: {p.usage.calls} calls · {p.usage.units} units · ${p.usage.cost_usd} · {p.usage.errors} errors</div>}
  </div>
}

export default function Integrations() {
  const list = useApi('/integrations')
  const [prov, setProv] = useState('')
  const ev = useApi('/integrations/events' + (prov ? '?provider=' + prov : ''), [prov])
  return <div className="page">
    <div className="head"><div><h1><em>Integrations</em></h1><p>Keys are stored encrypted on the server (or read from environment variables) and are never sent to the browser. A provider shows "connected" only after a successful live test.</p></div></div>
    <div className="grid g3" style={{ marginBottom: 16 }}>{(list.data || []).map(p => <Provider key={p.key} p={p} reload={() => { list.reload(); ev.reload() }} />)}</div>
    <div className="card"><div className="row between"><h2>Call and error log</h2>
      <select style={{ width: 180 }} value={prov} onChange={e => setProv(e.target.value)}><option value="">All providers</option>{['anthropic', 'youtube', 'pexels', 'pixabay', 'heygen', 'instagram'].map(p => <option key={p}>{p}</option>)}</select></div>
      {(ev.data || []).length === 0 ? <div className="muted small">No API activity yet.</div> :
        <table><thead><tr><th>When</th><th>Provider</th><th>Type</th><th>Result</th><th>Message</th><th>Units</th><th>Cost</th></tr></thead>
          <tbody>{ev.data.map(e => <tr key={e.id}><td className="small">{ago(e.at)}</td><td>{e.provider}</td><td>{e.kind}</td><td><Badge s={e.ok ? 'ok' : 'bad'}>{e.ok ? 'ok' : 'error'}</Badge></td><td className="small" style={{ maxWidth: 520 }}>{e.message}</td><td>{e.units || ''}</td><td>{e.cost_usd ? '$' + e.cost_usd.toFixed(4) : ''}</td></tr>)}</tbody></table>}
    </div>
  </div>
}
