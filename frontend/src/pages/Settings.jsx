import { useState, useEffect } from 'react'
import { api, act, useApi, CATEGORIES, MARKETS } from '../lib.jsx'

export default function Settings() {
  const prefs = useApi('/settings/preferences')
  const avatar = useApi('/settings/avatar_profile')
  const music = useApi('/assets?kind=music')
  const [p, setP] = useState(null)
  const [a, setA] = useState('')
  useEffect(() => { if (prefs.data) setP(prefs.data) }, [prefs.data])
  useEffect(() => { if (avatar.data) setA(JSON.stringify(Object.fromEntries(Object.entries(avatar.data).filter(([k]) => !k.startsWith('_'))), null, 2)) }, [avatar.data])
  if (!p) return <div className="page muted">Loading…</div>
  const u = (k, v) => setP({ ...p, [k]: v })
  const ue = (k, v) => setP({ ...p, export: { ...p.export, [k]: v } })
  const toggle = (k, v) => u(k, p[k].includes(v) ? p[k].filter(x => x !== v) : [...p[k], v])
  const save = async () => { await act(() => api('/settings/preferences', { method: 'PUT', body: { value: p } }), 'Settings saved. New projects inherit them.') }
  const saveAvatar = async () => { let v; try { v = JSON.parse(a) } catch { return alert('Invalid JSON') } await act(() => api('/settings/avatar_profile', { method: 'PUT', body: { value: v } }), 'Avatar & voice configuration saved') }
  return <div className="page">
    <div className="head"><div><h1><em>Settings</em></h1><p>Saved permanently. Every new project inherits these, with no rebuild needed. Editing style lives in Editing Templates; API keys live in Integrations.</p></div>
      <button className="btn primary" onClick={save}>Save settings</button></div>
    <div className="grid g2">
      <div className="card"><h2>Video defaults</h2>
        <div className="grid g2">
          <div className="field"><label>Min duration (s)</label><input type="number" value={p.default_duration_s[0]} onChange={e => u('default_duration_s', [+e.target.value, p.default_duration_s[1]])} /></div>
          <div className="field"><label>Max duration (s)</label><input type="number" value={p.default_duration_s[1]} onChange={e => u('default_duration_s', [p.default_duration_s[0], +e.target.value])} /></div>
          <div className="field"><label>Width</label><input type="number" value={p.export.width} onChange={e => ue('width', +e.target.value)} /></div>
          <div className="field"><label>Height</label><input type="number" value={p.export.height} onChange={e => ue('height', +e.target.value)} /></div>
          <div className="field"><label>Frame rate</label><input type="number" value={p.export.fps} onChange={e => ue('fps', +e.target.value)} /></div>
          <div className="field"><label>Quality (CRF, lower = better)</label><input type="number" value={p.export.crf} onChange={e => ue('crf', +e.target.value)} /></div>
        </div>
        <div className="small dim">Export: MP4, H.264 High, AAC {p.export.abitrate}, 9:16, no watermark. Canvas size and fps for rendering come from the editing style.</div>
        <label className="row" style={{ marginTop: 10 }}><input type="checkbox" style={{ width: 'auto' }} checked={p.require_final_approval} onChange={e => u('require_final_approval', e.target.checked)} /> Require my approval before final export</label>
      </div>
      <div className="card"><h2>Content focus</h2>
        <label>Preferred categories</label><div className="row" style={{ marginBottom: 12 }}>{CATEGORIES.map(c => <button key={c} className={'chip ' + (p.categories.includes(c) ? 'on' : '')} onClick={() => toggle('categories', c)}>{c}</button>)}</div>
        <label>Target marketplaces</label><div className="row">{MARKETS.map(([k, l]) => <button key={k} className={'chip ' + (p.markets.includes(k) ? 'on' : '')} onClick={() => toggle('markets', k)}>{l}</button>)}</div>
      </div>
      <div className="card"><h2>Roman Urdu subtitles</h2>
        <div className="field"><label>Language mode</label><select value={p.language} onChange={e => u('language', e.target.value)}><option value="roman_urdu">Roman Urdu (Latin script only)</option><option value="auto">Auto-detect (for English-only videos)</option></select></div>
        <div className="field"><label>Spelling prompt for speech recognition (Roman Urdu examples of your vocabulary)</label><textarea rows={4} value={p.whisper_prompt} onChange={e => u('whisper_prompt', e.target.value)} /></div>
        <div className="small dim">Fonts, colours and placement are in Editing Templates → Subtitles.</div>
      </div>
      <div className="card"><h2>AI, B-roll and audio</h2>
        <div className="grid g2">
          <div className="field"><label>Claude model</label><select value={p.claude_model} onChange={e => u('claude_model', e.target.value)}>{['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'].map(m => <option key={m}>{m}</option>)}</select></div>
          <div className="field"><label>Claude effort</label><select value={p.claude_effort} onChange={e => u('claude_effort', e.target.value)}>{['low', 'medium', 'high'].map(m => <option key={m}>{m}</option>)}</select></div>
        </div>
        <div className="field"><label>Default background music</label><select value={p.audio?.music_asset_id || ''} onChange={e => u('audio', { ...p.audio, music_asset_id: e.target.value ? +e.target.value : null })}>
          <option value="">Generated ambient pad</option>{(music.data || []).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></div>
        <div className="small dim">B-roll source order: your library → Pexels → typographic graphics. Voice, music and SFX levels are in Editing Templates → Audio.</div>
      </div>
      <div className="card" style={{ gridColumn: 'span 2' }}><div className="row between"><h2>Avatar & voice configuration</h2><button className="btn" onClick={saveAvatar}>Save avatar config</button></div>
        <textarea style={{ minHeight: 280, fontFamily: 'ui-monospace, monospace', fontSize: 12 }} value={a} onChange={e => setA(e.target.value)} /></div>
    </div>
  </div>
}
