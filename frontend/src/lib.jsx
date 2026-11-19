import { useEffect, useRef, useState, useCallback } from 'react'

export async function api(path, opts = {}) {
  const o = { ...opts }
  if (o.body && !(o.body instanceof FormData)) {
    o.headers = { 'content-type': 'application/json', ...(o.headers || {}) }
    o.body = JSON.stringify(o.body)
  }
  const r = await fetch('/api' + path, o)
  const ct = r.headers.get('content-type') || ''
  const data = ct.includes('json') ? await r.json() : await r.text()
  if (!r.ok) throw new Error((data && data.detail) || (typeof data === 'string' ? data : r.statusText))
  return data
}

export function useApi(path, deps = [], interval = 0) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    if (!path) { setLoading(false); return Promise.resolve() }
    return api(path).then(d => { setData(d); setError(null) }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [path])
  useEffect(() => { load() }, [load, ...deps])
  useEffect(() => {
    if (!interval) return
    const t = setInterval(load, interval)
    return () => clearInterval(t)
  }, [load, interval])
  return { data, error, loading, reload: load, setData }
}

let toastSet = null
export function Toaster() {
  const [t, setT] = useState(null)
  toastSet = setT
  useEffect(() => { if (t) { const x = setTimeout(() => setT(null), 4500); return () => clearTimeout(x) } }, [t])
  return t ? <div className="toast" style={{ borderColor: t.err ? 'var(--bad)' : 'var(--line2)' }}>{t.msg}</div> : null
}
export const toast = (msg, err = false) => toastSet && toastSet({ msg, err })

export async function act(fn, ok) {
  try { const r = await fn(); if (ok) toast(ok); return r } catch (e) { toast(e.message, true); throw e }
}

export const Badge = ({ s, children }) => <span className={'badge ' + (s || '')}>{children || (s || '').replace(/_/g, ' ')}</span>

export const fmtN = n => n == null ? '—' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : String(n)
export const fmtT = t => t == null ? '—' : `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`
export const ago = iso => { if (!iso) return ''; const s = (Date.now() - new Date(iso)) / 1000; return s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago` }

export function Stages({ stages }) {
  return <div className="stages" title={stages.map(s => `${s.label}: ${s.status}`).join('\n')}>{stages.map(s => <i key={s.name} className={s.status} />)}</div>
}

export function Modal({ onClose, children, title }) {
  return <div className="modal-bg" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="modal">
      <div className="row between" style={{ marginBottom: 14 }}><h2>{title}</h2><button className="btn sm" onClick={onClose}>Close</button></div>
      {children}
    </div>
  </div>
}

export function Err({ e }) { return e ? <div className="err">{e}</div> : null }

export const CATEGORIES = ['Amazon', 'Shopify', 'China Sourcing', 'AI Automation', 'Product Hunting', 'E-commerce News', 'Business Case Studies', 'Tutorials']
export const MARKETS = [['SA', 'Saudi Arabia'], ['AE', 'UAE'], ['US', 'USA'], ['GB', 'UK'], ['CA', 'Canada'], ['AU', 'Australia'], ['JP', 'Japan']]

export function useJob(onDone) {
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const cb = useRef(onDone); cb.current = onDone
  useEffect(() => {
    if (!jobId) return
    const t = setInterval(async () => {
      const j = await api('/jobs/' + jobId).catch(() => null)
      if (!j) return
      setJob(j)
      if (j.status === 'done' || j.status === 'failed') {
        clearInterval(t); setJobId(null)
        if (j.status === 'failed') toast(j.error || 'Job failed', true)
        cb.current && cb.current(j)
      }
    }, 1500)
    return () => clearInterval(t)
  }, [jobId])
  return { start: id => { setJob({ status: 'queued' }); setJobId(id) }, running: !!jobId, job }
}
