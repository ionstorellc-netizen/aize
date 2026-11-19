import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api, act, useApi, Badge, fmtN, Err, CATEGORIES, MARKETS, useJob } from '../lib.jsx'

const Score = ({ s }) => s ? <span title={s.unit || ''}>{s.value == null ? '—' : typeof s.value === 'number' ? fmtN(s.value) : s.value} <Badge s={s.label} /></span> : '—'

export default function Research() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const runs = useApi('/research', [], 4000)
  const integ = useApi('/integrations')
  const [sel, setSel] = useState(null)
  const run = useApi(sel ? '/research/' + sel : null, [sel])
  const [f, setF] = useState({ query: '', categories: ['Amazon', 'China Sourcing'], markets: ['SA', 'AE'] })
  const job = useJob(() => { runs.reload(); run.reload() })
  const yt = integ.data?.find(i => i.key === 'youtube')
  const claudeOk = ['connected', 'configured_untested'].includes(integ.data?.find(i => i.key === 'anthropic')?.state)
  useEffect(() => { if (!sel && runs.data?.length) setSel(runs.data[0].id) }, [runs.data])
  const toggle = (k, v) => setF(x => ({ ...x, [k]: x[k].includes(v) ? x[k].filter(y => y !== v) : [...x[k], v] }))
  const start = async () => {
    const r = await act(() => api('/research', { method: 'POST', body: f }), 'Research started')
    setSel(r.id); job.start(r.job_id); runs.reload()
  }
  const genIdeas = async () => {
    const r = await act(() => api('/ideas/generate', { method: 'POST', body: { research_run_id: sel, n: 10 } }), 'Generating ideas from this research…')
    nav('/ideas?job=' + r.job_id)
  }
  const res = run.data?.result
  return <div className="page">
    <div className="head"><div><h1>Viral <em>Research</em></h1><p>Finds high-performing e-commerce shorts and channels through the official YouTube Data API. Every number below is labelled verified, estimated or unavailable. Nothing is invented.</p></div></div>
    {yt && yt.state === 'not_configured' && <div className="note" style={{ marginBottom: 16 }}>YouTube Data API key is missing, so research cannot run. Add it in <a href="/integrations">Integrations</a> (free, 10,000 units/day).</div>}
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="grid g2">
        <div><div className="field"><label>Focus keyword (optional)</label><input value={f.query} onChange={e => setF({ ...f, query: e.target.value })} placeholder="e.g. amazon saudi private label" /></div>
          <label>Categories</label><div className="row">{CATEGORIES.map(c => <button key={c} className={'chip ' + (f.categories.includes(c) ? 'on' : '')} onClick={() => toggle('categories', c)}>{c}</button>)}</div></div>
        <div><label>Marketplaces (YouTube region)</label><div className="row" style={{ marginBottom: 14 }}>{MARKETS.map(([k, l]) => <button key={k} className={'chip ' + (f.markets.includes(k) ? 'on' : '')} onClick={() => toggle('markets', k)}>{l}</button>)}</div>
          <div className="dim small">Uses up to 8 searches x 2 regions (about 1,600 of your 10,000 daily YouTube units).</div>
          <button className="btn primary" style={{ marginTop: 12 }} disabled={job.running || yt?.state === 'not_configured'} onClick={start}>{job.running ? 'Researching…' : 'Start viral research'}</button></div>
      </div>
      {job.job?.log && job.running && <div className="pre" style={{ marginTop: 12 }}>{job.job.log}</div>}
    </div>

    <div className="row" style={{ marginBottom: 12 }}>{(runs.data || []).map(r => <button key={r.id} className={'chip ' + (sel === r.id ? 'on' : '')} onClick={() => setSel(r.id)}>#{r.id} {r.query || r.categories.join(', ')} <Badge s={r.status} /></button>)}</div>
    {run.data?.error && <Err e={run.data.error} />}
    {res && <>
      <div className="row between" style={{ margin: '8px 0 12px' }}>
        <div className="muted">{res.video_count} verified videos · {res.competitors.length} channels · queries: {res.queries.join(', ')}</div>
        <button className="btn green" disabled={!claudeOk} title={claudeOk ? '' : 'Needs Claude'} onClick={genIdeas}>Generate ideas from this research</button>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Top {res.opportunities.length} video opportunities</h2>
        <table><thead><tr><th>#</th><th>Opportunity</th><th>Interest</th><th>Recent popularity</th><th>Engagement</th><th>Search demand</th><th>Originality</th><th>Edu value</th><th>Relevance</th><th>Sources</th></tr></thead>
          <tbody>{res.opportunities.map((o, i) => <tr key={i}><td>{i + 1}</td>
            <td style={{ maxWidth: 320 }}><b>{o.title}</b>{o.category && <> <Badge>{o.category}</Badge></>}<div className="small muted">{o.why_now || o.proven_hook}</div>
              {o.verified_metrics?.map(m => <div key={m.url} className="small dim">{fmtN(m.views)} views · {fmtN(m.likes)} likes · {fmtN(m.comments)} comments <Badge s="verified" /></div>)}</td>
            {['audience_interest', 'recent_popularity', 'engagement_signals', 'search_demand', 'content_originality', 'educational_value', 'audience_relevance'].map(k => <td key={k} className="small"><Score s={o.scores[k]} /></td>)}
            <td>{o.source_urls.map((u, j) => <div key={j}><a href={u} target="_blank">link {j + 1}</a></div>)}</td></tr>)}</tbody></table>
        <div className="dim small" style={{ marginTop: 8 }}>{res.opportunities[0]?.ranking_method}</div>
      </div>
      <div className="grid g3" style={{ marginBottom: 16 }}>
        {[['Audience questions', 'audience_questions'], ['Trending subjects', 'trending_subjects'], ['Recent hook patterns', 'hook_patterns']].map(([l, k]) =>
          <div className="card" key={k}><h2>{l} <Badge s={res.insights.label.split(' ')[0]} /></h2>
            {res.insights[k].length ? <ul style={{ paddingLeft: 18, margin: 0 }}>{res.insights[k].map((x, i) => <li key={i}>{x}</li>)}</ul> : <div className="muted small">{res.insights.label}</div>}</div>)}
      </div>
      <div className="card"><h2>High-view videos found</h2>
        <table><thead><tr><th>Video</th><th>Channel</th><th>Published</th><th>Views</th><th>Likes</th><th>Comments</th><th>Views/day</th><th>Eng. %</th></tr></thead>
          <tbody>{res.videos.slice(0, 60).map(v => <tr key={v.id}><td style={{ maxWidth: 380 }}><a href={v.url} target="_blank">{v.title}</a></td><td>{v.channel}</td>
            <td className="small">{v.published_at?.slice(0, 10)}</td><td>{fmtN(v.views)}</td><td>{fmtN(v.likes)}</td><td>{fmtN(v.comments)}</td><td>{fmtN(v.views_per_day)}</td><td>{v.engagement_rate ?? '—'}</td></tr>)}</tbody></table>
        <div className="dim small" style={{ marginTop: 8 }}>{res.notes.join(' ')}</div></div>
    </>}
    {!res && !run.data?.error && <div className="empty">No research results yet.</div>}
  </div>
}
