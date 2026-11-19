import { useState, useEffect } from 'react'
import { api, act, useApi } from '../lib.jsx'

const get = (o, p) => p.split('.').reduce((a, k) => a?.[k], o)
const setp = (o, p, v) => { const ks = p.split('.'); let x = o; ks.slice(0, -1).forEach(k => x = x[k]); x[ks.at(-1)] = v }

const FIELDS = [
  ['Pacing', [['pacing.remove_pauses_longer_than', 'Remove pauses longer than (s)', 'n'], ['pacing.keep_padding', 'Breath padding kept (s)', 'n'], ['pacing.angle_change_every_s', 'Re-frame every (min,max s)', 'arr']]],
  ['Camera', [['camera.framing_pattern', 'Framing pattern', 'arr'], ['camera.framings', 'Framings (JSON)', 'json']]],
  ['Subtitles', [['subtitles.font_size', 'Font size', 'n'], ['subtitles.max_words_per_line', 'Max words per caption', 'n'], ['subtitles.max_chars_per_line', 'Max characters', 'n'], ['subtitles.position_y_ratio', 'Vertical position (0 top – 1 bottom)', 'n'],
    ['subtitles.box_color', 'Box colour', 'c'], ['subtitles.text_color', 'Spoken word colour', 'c'], ['subtitles.active_word_color', 'Active word colour', 'c'], ['subtitles.upcoming_word_color', 'Upcoming word colour', 'c'], ['subtitles.uppercase', 'Uppercase', 'b'], ['subtitles.box', 'Box behind text', 'b']]],
  ['Titles', [['titles.hook_font_size', 'Hook size', 'n'], ['titles.keyword_font_size', 'Keyword size', 'n'], ['titles.position_y_ratio', 'Keyword vertical position', 'n'], ['titles.duration_s', 'Hook duration (s)', 'n']]],
  ['B-roll', [['broll.coverage_target', 'Coverage target (0–1)', 'n'], ['broll.card_ratio', 'Share as floating cards (0–1)', 'n'], ['broll.min_len_s', 'Min clip length (s)', 'n'], ['broll.max_len_s', 'Max clip length (s)', 'n'], ['broll.gap_s', 'Gap between clips (min,max s)', 'arr'], ['broll.card.width_ratio', 'Card width (0–1)', 'n'], ['broll.card.y_ratio', 'Card top position', 'n'], ['broll.card.corner_radius', 'Card corner radius', 'n'], ['broll.card.border_color', 'Card border colour', 'c']]],
  ['Palette & grade', [['palette.primary', 'Brand green', 'c'], ['palette.cream', 'Cream', 'c'], ['palette.gold', 'Gold', 'c'], ['grade.contrast', 'Contrast', 'n'], ['grade.saturation', 'Saturation', 'n'], ['grade.warmth', 'Warmth', 'n'], ['grade.vignette', 'Vignette', 'n']]],
  ['Audio & CTA', [['audio.voice_target_lufs', 'Voice loudness (LUFS)', 'n'], ['audio.voice_true_peak_db', 'Voice true peak (dB)', 'n'], ['audio.music_db', 'Music level (dB)', 'n'], ['audio.sfx_db', 'SFX level (dB)', 'n'], ['audio.duck_music_during_speech', 'Duck music under speech', 'b'], ['cta.duration_s', 'CTA duration (s)', 'n'], ['cta.end_fade_s', 'End fade (s)', 'n']]],
]

export default function Templates() {
  const prof = useApi('/settings/style_profile')
  const [s, setS] = useState(null)
  const [raw, setRaw] = useState(false)
  const [rawText, setRawText] = useState('')
  useEffect(() => { if (prof.data) { setS(prof.data); setRawText(JSON.stringify(Object.fromEntries(Object.entries(prof.data).filter(([k]) => !k.startsWith('_'))), null, 2)) } }, [prof.data])
  if (!s) return <div className="page muted">Loading…</div>
  const upd = (p, v) => setS(x => { const y = structuredClone(x); setp(y, p, v); return y })
  const save = async () => { await act(() => api('/settings/style_profile', { method: 'PUT', body: { value: raw ? JSON.parse(rawText) : s } }), 'Editing style saved. New renders use it.'); prof.reload() }
  const reset = async () => { if (!confirm('Reset to the profile extracted from Reference 2?')) return; await act(() => api('/settings/style_profile/reset', { method: 'POST' }), 'Reset to reference default'); prof.reload() }
  return <div className="page">
    <div className="head"><div><h1>Editing <em>Templates</em></h1><p>The approved editing style, measured from your reference video. Every new project uses it by default. Changes apply to the next render, with no rebuild needed.</p></div>
      <div className="row"><button className="btn" onClick={() => setRaw(!raw)}>{raw ? 'Form view' : 'JSON view'}</button><button className="btn" onClick={reset}>Reset to reference</button><button className="btn primary" onClick={save}>Save style</button></div></div>
    <div className="grid" style={{ gridTemplateColumns: '300px 1fr', alignItems: 'start' }}>
      <div className="card"><h2>{s.name}</h2>
        {s._reference_video ? <video className="vid916" src={s._reference_video} controls muted /> : <div className="empty">Reference video not uploaded</div>}
        <p className="small muted">{s.notes}</p>
        <label>Upload a new style reference</label><input type="file" accept="video/*" onChange={async e => { const fd = new FormData(); fd.append('file', e.target.files[0]); await act(() => api('/settings/reference/style', { method: 'POST', body: fd }), 'Reference stored'); prof.reload() }} />
        <div className="small dim" style={{ marginTop: 6 }}>Uploading a new reference stores it for comparison; the measured values here are what the engine uses.</div>
      </div>
      {raw ? <textarea style={{ minHeight: 700, fontFamily: 'ui-monospace, monospace', fontSize: 12 }} value={rawText} onChange={e => setRawText(e.target.value)} /> :
        <div className="grid g2">{FIELDS.map(([title, fs]) => <div className="card" key={title}><h2>{title}</h2>
          {fs.map(([p, l, t]) => { const v = get(s, p); return <div className="field" key={p}><label>{l}</label>
            {t === 'n' ? <input type="number" step="any" value={v ?? ''} onChange={e => upd(p, +e.target.value)} /> :
              t === 'b' ? <input type="checkbox" style={{ width: 'auto' }} checked={!!v} onChange={e => upd(p, e.target.checked)} /> :
                t === 'c' ? <div className="row"><input type="color" style={{ width: 44, padding: 2 }} value={v} onChange={e => upd(p, e.target.value)} /><input value={v} onChange={e => upd(p, e.target.value)} style={{ width: 110 }} /></div> :
                  t === 'arr' ? <input value={(v || []).join(', ')} onChange={e => upd(p, e.target.value.split(',').map(x => isNaN(+x) || x.trim() === '' ? x.trim() : +x))} /> :
                    <textarea value={JSON.stringify(v)} onChange={e => { try { upd(p, JSON.parse(e.target.value)) } catch { } }} />}</div> })}</div>)}</div>}
    </div>
  </div>
}
