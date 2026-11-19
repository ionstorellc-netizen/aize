import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, act, useApi, Badge, fmtT, useJob, Modal } from '../lib.jsx'

const uid = () => Math.random().toString(16).slice(2, 10)
const FRAMING = { wide: 1.0, medium: 1.14, close: 1.32 }

// JS port of backend edl.resolved(): source-anchored items -> timeline time
function resolve(edl) {
  const spans = []; let t = 0
  for (const s of edl.segments) { spans.push([s.src_in, s.src_out, t]); t += s.src_out - s.src_in }
  const f = x => { for (const [a, b, o] of spans) if (x >= a - 1e-3 && x < b) return o + (x - a); return null }
  const out = { duration: t, segments: [], broll: [], titles: [], sfx: [], subtitles: [] }
  let tt = 0
  edl.segments.forEach((s, i) => { const d = s.src_out - s.src_in; out.segments.push({ ...s, i, t: tt, dur: d }); tt += d })
  for (const k of ['broll', 'titles', 'sfx']) (edl[k] || []).forEach((o, i) => { const x = f(o.src_t); if (x != null) out[k].push({ ...o, i, t: x }) })
  ;(edl.subtitles || []).forEach((ph, i) => {
    const ws = ph.words.map(w => ({ w: w.w, t0: f(w.s), t1: f(Math.max(w.s, w.e - 0.01)) })).filter(w => w.t0 != null)
    if (ws.length) out.subtitles.push({ i, t0: ws[0].t0, t1: (ws[ws.length - 1].t1 ?? ws[ws.length - 1].t0) + 0.01, text: ph.words.map(w => w.w).join(' ') })
  })
  return out
}
const tl2src = (edl, t) => { let o = 0; for (const s of edl.segments) { const d = s.src_out - s.src_in; if (t >= o && t < o + d) return s.src_in + (t - o); o += d } return null }

export default function Editor() {
  const { pid } = useParams()
  const nav = useNavigate()
  const projects = useApi('/projects')
  const withEdit = (projects.data || []).filter(p => p.stages.find(s => s.name === 'video_editing' && s.status === 'completed'))
  const [edl, setEdl] = useState(null)
  const [hist, setHist] = useState({ past: [], future: [] })
  const [dirty, setDirty] = useState(false)
  const [sel, setSel] = useState(null)
  const [time, setTime] = useState(0)
  const [zoom, setZoom] = useState(22)
  const [picker, setPicker] = useState(null)
  const [src, setSrc] = useState('preview')
  const [ver, setVer] = useState(0)
  const vref = useRef()
  const proj = useApi(pid ? '/projects/' + pid : null, [pid, ver])
  const lib = useApi('/assets?kind=broll,image')
  const music = useApi('/assets?kind=music')
  const job = useJob(() => setVer(v => v + 1))

  useEffect(() => { if (!pid && withEdit.length) nav('/editor/' + withEdit[0].id, { replace: true }) }, [pid, withEdit.length])
  useEffect(() => {
    if (!pid) return
    api(`/projects/${pid}/edl`).then(d => { setEdl(d.edl); setHist({ past: [], future: [] }); setDirty(false); setSel(null) }).catch(() => setEdl(null))
  }, [pid])
  useEffect(() => {
    const k = e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo() }
      if (e.key === ' ' && vref.current) { e.preventDefault(); vref.current.paused ? vref.current.play() : vref.current.pause() }
    }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  })
  const res = useMemo(() => edl ? resolve(edl) : null, [edl])

  const change = fn => {
    setHist(h => ({ past: [...h.past.slice(-80), JSON.stringify(edl)], future: [] }))
    const y = JSON.parse(JSON.stringify(edl)); fn(y); setEdl(y); setDirty(true)
  }
  const undo = () => { if (!hist.past.length) return; setHist(h => ({ past: h.past.slice(0, -1), future: [JSON.stringify(edl), ...h.future] })); setEdl(JSON.parse(hist.past[hist.past.length - 1])); setDirty(true) }
  const redo = () => { if (!hist.future.length) return; setHist(h => ({ past: [...h.past, JSON.stringify(edl)], future: h.future.slice(1) })); setEdl(JSON.parse(hist.future[0])); setDirty(true) }
  const save = async () => { await act(() => api(`/projects/${pid}/edl`, { method: 'PUT', body: { edl } }), 'Edit saved'); setDirty(false) }
  const preview = async () => { if (dirty) await save(); const r = await act(() => api(`/projects/${pid}/preview`, { method: 'POST' }), 'Rendering preview…'); job.start(r.job_id); setSrc('preview') }
  const exportFinal = async () => { if (dirty) await save(); await act(() => api(`/projects/${pid}/export`, { method: 'POST' }), 'Final render + QC started'); nav('/queue/' + pid) }
  const seek = t => { setTime(t); if (vref.current) vref.current.currentTime = t }

  if (!pid) return <div className="page"><div className="head"><div><h1>Video <em>Editor</em></h1></div></div>
    {withEdit.length === 0 ? <div className="empty">No edited projects yet. A project appears here once it reaches the Video editing stage.</div> : 'Loading…'}</div>
  if (!edl || !res) return <div className="page muted">{proj.data && !proj.data.has_edl ? 'This project has no edit yet. Run it up to the Video editing stage.' : 'Loading…'}</div>
  const P = proj.data || {}
  const vsrc = (src === 'preview' ? P.preview : src === 'master' ? P.master : P.avatar) || P.preview || P.master || P.avatar
  const W = Math.max(600, res.duration * zoom)
  const x = t => t * zoom
  const S = sel && (sel.type === 'segments' ? edl.segments[sel.i] : sel.type === 'subtitles' ? edl.subtitles[sel.i] : (edl[sel.type] || [])[sel.i])
  const selItem = sel && res[sel.type]?.find(o => o.i === sel.i)

  const addAt = (kind) => change(e => {
    const s = tl2src(e, time) ?? e.segments[0].src_in
    if (kind === 'title') e.titles.push({ id: uid(), kind: 'keyword', src_t: s, dur: 1.4, text: 'KEYWORD', sub: '' })
    if (kind === 'sfx') e.sfx.push({ id: uid(), src_t: s, kind: 'whoosh' })
  })

  return <div className="page" style={{ maxWidth: 'none' }}>
    <div className="head">
      <div><h1>Video <em>Editor</em></h1><div className="row" style={{ marginTop: 8 }}>
        <select style={{ width: 320 }} value={pid} onChange={e => nav('/editor/' + e.target.value)}>{withEdit.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select>
        <span className="muted">{res.duration.toFixed(1)}s · {edl.segments.length} shots · {res.broll.length} B-roll · {res.subtitles.length} captions · style: {edl.style_name}</span></div></div>
      <div className="row">
        <button className="btn" disabled={!hist.past.length} onClick={undo}>Undo</button>
        <button className="btn" disabled={!hist.future.length} onClick={redo}>Redo</button>
        <button className="btn" disabled={!dirty} onClick={save}>Save</button>
        <button className="btn green" disabled={job.running} onClick={preview}>{job.running ? 'Rendering…' : 'Render preview'}</button>
        <button className="btn primary" onClick={exportFinal}>Export final MP4</button>
      </div>
    </div>
    {res.duration > 50.5 && <div className="note" style={{ marginBottom: 10 }}>The cut is {res.duration.toFixed(1)}s, over the 50s target. Delete or trim shots below.</div>}
    <div className="grid" style={{ gridTemplateColumns: '300px 1fr 330px', alignItems: 'start' }}>
      <div className="card" style={{ padding: 12 }}>
        <div className="tabs" style={{ marginBottom: 8 }}>{['preview', 'master', 'source'].map(k => <button key={k} className={src === k ? 'on' : ''} onClick={() => setSrc(k)}>{k}</button>)}</div>
        {vsrc ? <video key={vsrc + ver} ref={vref} className="vid916" src={vsrc + '?v=' + ver} controls onTimeUpdate={e => src !== 'source' && setTime(e.target.currentTime)} /> : <div className="empty">Render a preview</div>}
        <div className="small dim" style={{ marginTop: 6 }}>{dirty ? 'Unsaved edits: the preview shows the last render.' : 'Space = play/pause, Ctrl+Z / Ctrl+Shift+Z = undo/redo'}</div>
        {job.running && <div className="pre" style={{ marginTop: 8 }}>{job.job?.log || 'queued…'}</div>}
      </div>

      <div className="col" style={{ minWidth: 0 }}>
        <div className="row between"><div className="row">
          <span className="gold">{fmtT(time)}</span>
          <button className="btn sm" onClick={() => setPicker({ mode: 'add' })}>+ B-roll at playhead</button>
          <button className="btn sm" onClick={() => addAt('title')}>+ Text callout</button>
          <button className="btn sm" onClick={() => addAt('sfx')}>+ Sound effect</button>
          <button className="btn sm" onClick={() => { const seg = res.segments.find(s => time > s.t + 0.2 && time < s.t + s.dur - 0.2); if (!seg) return; change(e => { const s = e.segments[seg.i]; const cut = s.src_in + (time - seg.t); e.segments.splice(seg.i + 1, 0, { ...s, id: uid(), src_in: cut }); s.src_out = cut }) }}>Split shot</button>
        </div><div className="row"><span className="dim small">zoom</span><input type="range" min="8" max="60" value={zoom} onChange={e => setZoom(+e.target.value)} style={{ width: 120 }} /></div></div>
        <div className="tl" onClick={e => { if (e.target.classList.contains('lane') || e.target.classList.contains('ruler')) { const r = e.currentTarget.getBoundingClientRect(); seek(Math.max(0, (e.clientX - r.left - 80 + e.currentTarget.scrollLeft) / zoom)) } }}>
          <div style={{ width: W, position: 'relative' }}>
            <div className="ruler">{Array.from({ length: Math.ceil(res.duration / 5) + 1 }, (_, i) => <span key={i} style={{ left: x(i * 5) }}>{i * 5}s</span>)}</div>
            {[['Shots', 'segments', o => `${o.framing} ${o.dur.toFixed(1)}s`, o => 'seg ' + o.framing, o => o.dur],
              ['B-roll', 'broll', o => o.label || o.query || o.source, o => 'br ' + o.mode, o => o.dur],
              ['Text', 'titles', o => o.text, () => 'ti', o => o.dur],
              ['Captions', 'subtitles', o => o.text, () => 'sub', o => o.t1 - o.t0],
              ['SFX', 'sfx', () => '', () => 'sfx', () => 0.3]].map(([lbl, key, txt, cls, dur]) =>
              <div className="lane" key={key}><span className="lbl">{lbl}</span>
                {res[key].map(o => { const t0 = key === 'subtitles' ? o.t0 : o.t; return <div key={key + o.i} title={txt(o)} className={'clip ' + cls(o) + (sel?.type === key && sel.i === o.i ? ' sel' : '')}
                  style={{ left: x(t0), width: Math.max(4, x(dur(o)) - 2) }} onClick={ev => { ev.stopPropagation(); setSel({ type: key, i: o.i }); seek(t0 + 0.01) }}>{txt(o)}</div> })}
              </div>)}
            <div className="playhead" style={{ left: x(time) }} />
          </div>
        </div>

        <div className="grid g3">
          <div className="card"><h3 style={{ marginBottom: 10 }}>Audio</h3>
            <label>Music</label><select value={edl.audio.music === 'library' ? 'lib:' + edl.audio.music_asset_id : edl.audio.music} onChange={e => change(d => { const v = e.target.value; if (v.startsWith('lib:')) { d.audio.music = 'library'; d.audio.music_asset_id = +v.slice(4) } else { d.audio.music = v; d.audio.music_asset_id = null; d.audio.music_path = null } })}>
              <option value="generated_pad">Generated ambient pad</option><option value="none">No music</option>
              {(music.data || []).map(m => <option key={m.id} value={'lib:' + m.id}>{m.name}</option>)}</select>
            <label style={{ marginTop: 8 }}>Music level: {edl.audio.music_db} dB</label><input type="range" min="-40" max="-15" value={edl.audio.music_db} onChange={e => change(d => d.audio.music_db = +e.target.value)} />
            <label>SFX level: {edl.audio.sfx_db} dB</label><input type="range" min="-40" max="-12" value={edl.audio.sfx_db} onChange={e => change(d => d.audio.sfx_db = +e.target.value)} />
            <label>Voice loudness target: {edl.audio.voice_lufs} LUFS</label><input type="range" min="-20" max="-12" value={edl.audio.voice_lufs} onChange={e => change(d => d.audio.voice_lufs = +e.target.value)} />
            <label className="row"><input type="checkbox" style={{ width: 'auto' }} checked={edl.audio.duck} onChange={e => change(d => d.audio.duck = e.target.checked)} /> Duck music under speech</label>
          </div>
          <div className="card"><h3 style={{ marginBottom: 10 }}>Colour grade</h3>
            {[['contrast', 0.8, 1.3, 0.01], ['saturation', 0.6, 1.4, 0.01], ['brightness', -0.1, 0.1, 0.005], ['warmth', -0.1, 0.12, 0.005], ['vignette', 0, 0.8, 0.05]].map(([k, a, b, st]) =>
              <div key={k}><label>{k}: {edl.grade[k]}</label><input type="range" min={a} max={b} step={st} value={edl.grade[k] ?? 0} onChange={e => change(d => d.grade[k] = +e.target.value)} /></div>)}
          </div>
          <div className="card"><h3 style={{ marginBottom: 10 }}>Call to action (end card)</h3>
            <label>Text</label><input value={edl.cta?.text || ''} onChange={e => change(d => d.cta.text = e.target.value)} />
            <label style={{ marginTop: 8 }}>Comment bubble</label><input value={edl.cta?.sub || ''} onChange={e => change(d => d.cta.sub = e.target.value)} />
            <label style={{ marginTop: 8 }}>Duration: {edl.cta?.dur}s</label><input type="range" min="2" max="10" step="0.5" value={edl.cta?.dur || 6} onChange={e => change(d => d.cta.dur = +e.target.value)} />
            {edl.dropped_sentences?.length > 0 && <details style={{ marginTop: 10 }}><summary className="small muted">{edl.dropped_sentences.length} sentences removed by the auto-cut</summary>
              <ul className="small dim" style={{ paddingLeft: 16 }}>{edl.dropped_sentences.map((s, i) => <li key={i}>{s}</li>)}</ul></details>}
          </div>
        </div>
      </div>

      <div className="card" style={{ position: 'sticky', top: 12 }}>
        {!S ? <div className="muted">Select a clip on the timeline to edit it.</div> : <>
          <div className="row between" style={{ marginBottom: 10 }}><h2 style={{ margin: 0, textTransform: 'capitalize' }}>{sel.type === 'segments' ? 'Shot' : sel.type === 'subtitles' ? 'Caption' : sel.type === 'titles' ? 'Text' : sel.type}</h2>
            <button className="btn sm danger" onClick={() => { if (sel.type === 'segments' && edl.segments.length < 2) return; change(e => e[sel.type].splice(sel.i, 1)); setSel(null) }}>Delete</button></div>
          {sel.type === 'segments' && <>
            <label>Framing (digital camera angle)</label>
            <div className="row" style={{ marginBottom: 10 }}>{Object.keys(FRAMING).map(k => <button key={k} className={'chip ' + (S.framing === k ? 'on' : '')} onClick={() => change(e => { e.segments[sel.i].framing = k; e.segments[sel.i].zoom = FRAMING[k] })}>{k}</button>)}</div>
            <label>Custom zoom: {S.zoom}x</label><input type="range" min="1" max="1.6" step="0.02" value={S.zoom} onChange={e => change(d => d.segments[sel.i].zoom = +e.target.value)} />
            <div className="grid g2"><div><label>In (source s)</label><input type="number" step="0.05" value={S.src_in} onChange={e => change(d => d.segments[sel.i].src_in = Math.min(+e.target.value, S.src_out - 0.1))} /></div>
              <div><label>Out (source s)</label><input type="number" step="0.05" value={S.src_out} onChange={e => change(d => d.segments[sel.i].src_out = Math.max(+e.target.value, S.src_in + 0.1))} /></div></div>
            <div className="row" style={{ marginTop: 10 }}><button className="btn sm" disabled={sel.i === 0} onClick={() => { change(e => { const [s] = e.segments.splice(sel.i, 1); e.segments.splice(sel.i - 1, 0, s) }); setSel({ ...sel, i: sel.i - 1 }) }}>Move earlier</button>
              <button className="btn sm" disabled={sel.i === edl.segments.length - 1} onClick={() => { change(e => { const [s] = e.segments.splice(sel.i, 1); e.segments.splice(sel.i + 1, 0, s) }); setSel({ ...sel, i: sel.i + 1 }) }}>Move later</button></div>
            <div className="small dim" style={{ marginTop: 8 }}>Duration {(S.src_out - S.src_in).toFixed(2)}s. Captions, B-roll and text stay locked to the spoken words when shots move.</div>
          </>}
          {sel.type === 'broll' && <>
            {S.url && (S.media === 'image' ? <img src={S.url} style={{ width: '100%', borderRadius: 10 }} /> : <video src={S.url} style={{ width: '100%' }} muted autoPlay loop />)}
            <div className="small dim" style={{ margin: '6px 0' }}>{S.source} {S.query && `· "${S.query}"`}</div>
            <label>Placement</label><div className="row" style={{ marginBottom: 8 }}>{['card', 'full'].map(m => <button key={m} className={'chip ' + (S.mode === m ? 'on' : '')} onClick={() => change(e => e.broll[sel.i].mode = m)}>{m === 'card' ? 'Floating card' : 'Full screen'}</button>)}</div>
            <label>Duration: {S.dur}s</label><input type="range" min="0.8" max="5" step="0.1" value={S.dur} onChange={e => change(d => d.broll[sel.i].dur = +e.target.value)} />
            <div className="row"><button className="btn sm" onClick={() => change(e => e.broll[sel.i].src_t -= 0.25)}>◀ 0.25s</button><button className="btn sm" onClick={() => change(e => e.broll[sel.i].src_t += 0.25)}>0.25s ▶</button>
              <button className="btn sm primary" onClick={() => setPicker({ mode: 'replace', i: sel.i })}>Replace clip</button></div>
          </>}
          {sel.type === 'titles' && <>
            <label>Style</label><div className="row" style={{ marginBottom: 8 }}>{[['hook', 'Giant serif headline'], ['keyword', 'Keyword bar']].map(([k, l]) => <button key={k} className={'chip ' + (S.kind === k ? 'on' : '')} onClick={() => change(e => e.titles[sel.i].kind = k)}>{l}</button>)}</div>
            <label>Text</label><input value={S.text} onChange={e => change(d => d.titles[sel.i].text = e.target.value)} />
            <label style={{ marginTop: 8 }}>Second line (serif italic, optional)</label><input value={S.sub || ''} onChange={e => change(d => d.titles[sel.i].sub = e.target.value)} />
            <label style={{ marginTop: 8 }}>Duration: {S.dur}s</label><input type="range" min="0.6" max="4" step="0.1" value={S.dur} onChange={e => change(d => d.titles[sel.i].dur = +e.target.value)} />
          </>}
          {sel.type === 'subtitles' && <>
            <label>Caption text (Roman Urdu)</label>
            <textarea defaultValue={S.words.map(w => w.w).join(' ')} key={sel.i + JSON.stringify(S.words.map(w => w.w))} onBlur={e => {
              const nw = e.target.value.trim().split(/\s+/).filter(Boolean); if (!nw.length) return
              change(d => { const ph = d.subtitles[sel.i]; if (nw.length === ph.words.length) nw.forEach((w, k) => ph.words[k].w = w); else { const a = ph.words[0].s, b = ph.words[ph.words.length - 1].e, st = (b - a) / nw.length; ph.words = nw.map((w, k) => ({ w, s: a + k * st, e: a + (k + 1) * st })) } })
            }} />
            <div className="small dim">Same word count keeps exact word timing; a different count spreads timing evenly across the phrase.</div>
            <table style={{ marginTop: 8 }}><tbody>{S.words.map((w, k) => <tr key={k}><td>{w.w}</td><td className="dim small">{w.s.toFixed(2)}–{w.e.toFixed(2)}</td></tr>)}</tbody></table>
          </>}
          {sel.type === 'sfx' && <>
            <label>Sound</label><select value={S.kind} onChange={e => change(d => d.sfx[sel.i].kind = e.target.value)}>{['whoosh', 'click', 'pop', 'impact', 'notify'].map(k => <option key={k}>{k}</option>)}</select>
            <audio src={`/media/sfx/${S.kind}.wav`} controls style={{ width: '100%', marginTop: 8 }} />
          </>}
        </>}
      </div>
    </div>

    {picker && <Modal title={picker.mode === 'add' ? 'Add B-roll at ' + fmtT(time) : 'Replace B-roll'} onClose={() => setPicker(null)}>
      {(lib.data || []).length === 0 ? <div className="empty">Your library is empty. Upload footage in the B-Roll Library (or import from Pexels there).</div> :
        <div className="grid g3">{lib.data.map(a => <div key={a.id} className="card" style={{ padding: 8, cursor: 'pointer' }} onClick={() => {
          change(e => {
            const item = { path: null, url: a.url, media: a.kind === 'image' ? 'image' : 'video', asset_id: a.id, source: a.source, label: a.name, query: '' }
            if (picker.mode === 'replace') Object.assign(e.broll[picker.i], item, { in: 0 })
            else { const s = tl2src(e, time); if (s != null) e.broll.push({ id: uid(), src_t: s, dur: 2.2, mode: 'card', in: 0, ...item }) }
          }); setPicker(null)
        }}>{a.kind === 'image' ? <img src={a.url} style={{ width: '100%', borderRadius: 8 }} /> : <video src={a.url} muted style={{ width: '100%' }} onMouseOver={e => e.target.play()} onMouseOut={e => e.target.pause()} />}
          <div className="small">{a.name}</div><div className="small dim">{a.source}</div></div>)}</div>}
    </Modal>}
  </div>
}
