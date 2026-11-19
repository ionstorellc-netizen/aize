import { useApi } from '../lib.jsx'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'

// validated (dataviz validate_palette.js, dark, surface #111614): all checks pass
const C1 = '#a8823a', C2 = '#4f9dce'
const axis = { stroke: '#5f6b64', fontSize: 11, tickLine: false, axisLine: false }
const tip = { contentStyle: { background: '#161d1a', border: '1px solid #2d3a33', borderRadius: 10, color: '#eef0ea' }, cursor: { fill: 'rgba(255,255,255,.04)' } }

export default function Analytics() {
  const { data: d } = useApi('/analytics')
  if (!d) return <div className="page muted">Loading…</div>
  const cost = Object.entries(d.cost_by_provider).map(([k, v]) => ({ provider: k, usd: v }))
  return <div className="page">
    <div className="head"><div><h1><em>Analytics</em></h1><p>{d.note}</p></div></div>
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Projects created and completed, last 30 days</h2>
      <div style={{ height: 260 }}><ResponsiveContainer><BarChart data={d.daily} barGap={2}>
        <CartesianGrid vertical={false} stroke="#1c2521" />
        <XAxis dataKey="date" {...axis} tickFormatter={v => v.slice(5)} interval={4} />
        <YAxis allowDecimals={false} {...axis} width={30} />
        <Tooltip {...tip} />
        <Legend wrapperStyle={{ fontSize: 12, color: '#8e9a93' }} />
        <Bar dataKey="created" name="Created" fill={C1} radius={[4, 4, 0, 0]} maxBarSize={14} />
        <Bar dataKey="completed" name="Completed" fill={C2} radius={[4, 4, 0, 0]} maxBarSize={14} />
      </BarChart></ResponsiveContainer></div>
    </div>
    <div className="grid g2">
      <div className="card"><h2>Stage performance</h2>
        <table><thead><tr><th>Stage</th><th>Completed</th><th>Failed</th><th>Attempts</th><th>Avg time</th></tr></thead>
          <tbody>{Object.entries(d.stages).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, ' ')}</td><td>{v.completed}</td><td style={{ color: v.failed ? 'var(--bad)' : '' }}>{v.failed}</td><td>{v.attempts}</td><td>{v.avg_seconds != null ? v.avg_seconds + 's' : '—'}</td></tr>)}</tbody></table></div>
      <div className="col">
        <div className="card"><h2>API spend by provider (USD)</h2>
          {cost.length === 0 ? <div className="muted small">No paid API calls recorded yet.</div> :
            <div style={{ height: 200 }}><ResponsiveContainer><BarChart data={cost} layout="vertical">
              <XAxis type="number" {...axis} /><YAxis type="category" dataKey="provider" {...axis} width={80} />
              <Tooltip {...tip} formatter={v => '$' + v.toFixed(4)} /><Bar dataKey="usd" name="USD" fill={C1} radius={[0, 4, 4, 0]} maxBarSize={18} />
            </BarChart></ResponsiveContainer></div>}</div>
        <div className="card"><h2>Finished video durations</h2>
          {d.durations.length === 0 ? <div className="muted small">No completed videos yet.</div> :
            <table><tbody>{d.durations.map(x => <tr key={x.id}><td>{x.title}</td><td>{x.duration?.toFixed(1)}s</td></tr>)}</tbody></table>}</div>
      </div>
    </div>
  </div>
}
