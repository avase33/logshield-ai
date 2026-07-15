"""Built-in real-time system health dashboard (zero-build React via CDN)."""

from __future__ import annotations

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>LogShield-AI — System Health</title>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<style>
  :root{--bg:#0a0e17;--panel:#111827;--panel2:#1b2536;--text:#e6edf6;--muted:#8b98b0;
        --accent:#4ea1ff;--good:#37d67a;--warn:#ffb020;--bad:#ff5470;--line:#20293c;}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:radial-gradient(1200px 600px at 80% -10%, #12203a, #0a0e17);color:var(--text)}
  header{padding:18px 26px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
  header h1{font-size:18px;margin:0;letter-spacing:.4px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--good);box-shadow:0 0 10px var(--good)}
  .badge{font-size:11px;color:var(--muted);border:1px solid var(--line);padding:3px 8px;border-radius:20px}
  button.reload{margin-left:auto;background:var(--accent);color:#04101f;border:none;font-weight:600;
                padding:8px 14px;border-radius:9px;cursor:pointer}
  .wrap{padding:22px 26px;max-width:1240px;margin:0 auto}
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:20px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
  .kpi .n{font-size:22px;font-weight:700}
  .kpi .l{font-size:11px;color:var(--muted);margin-top:3px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:18px}
  .card h2{font-size:13px;margin:0 0 12px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
  .row{display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}
  .row:last-child{border-bottom:none}
  .pill{font-size:10px;padding:2px 7px;border-radius:6px;background:var(--panel2)}
  .sev4{color:var(--bad)} .sev3{color:var(--warn)} .sev5{color:#fff;background:var(--bad);padding:2px 6px;border-radius:5px}
  .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--muted);
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .grow{flex:1;min-width:0}
  .chan{font-size:10px;text-transform:uppercase;padding:2px 7px;border-radius:6px;background:var(--panel2);color:var(--accent)}
  .bar{height:8px;border-radius:5px;background:var(--panel2);overflow:hidden}
  .bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--good),var(--warn),var(--bad))}
  .muted{color:var(--muted)}
  @media(max-width:900px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>
<div id="root"></div>
<script>
const {useState,useEffect}=React;const e=React.createElement;
const api=(p)=>fetch(p).then(r=>r.json());
const SEV={0:"TRACE",1:"DEBUG",2:"INFO",3:"WARN",4:"ERROR",5:"CRIT"};
function Kpi({n,l}){return e('div',{className:'kpi'},e('div',{className:'n'},n),e('div',{className:'l'},l));}
function App(){
  const [h,setH]=useState(null),[inc,setInc]=useState([]),[al,setAl]=useState([]),[tpl,setTpl]=useState([]),[loading,setL]=useState(true);
  async function load(){setL(true);
    const [hh,ii,aa,tt]=await Promise.all([api('/health'),api('/incidents'),api('/alerts?limit=10'),api('/templates?top=10')]);
    setH(hh);setInc(ii);setAl(aa);setTpl(tt);setL(false);}
  useEffect(()=>{load();const t=setInterval(load,5000);return()=>clearInterval(t);},[]);
  const lps=h?Math.round(h.logs_per_second).toLocaleString():'—';
  return e('div',null,
    e('header',null,e('span',{className:'dot'}),e('h1',null,'LogShield-AI'),
      e('span',{className:'badge'},'real-time telemetry health'),
      e('button',{className:'reload',onClick:load},loading?'…':'Refresh')),
    e('div',{className:'wrap'},
      e('div',{className:'kpis'},
        e(Kpi,{n:lps,l:'logs / sec'}),
        e(Kpi,{n:h?h.total_logs.toLocaleString():'—',l:'logs processed'}),
        e(Kpi,{n:h?(h.error_rate*100).toFixed(1)+'%':'—',l:'error rate'}),
        e(Kpi,{n:h?h.anomalies:'—',l:'anomalies'}),
        e(Kpi,{n:h?h.unique_templates:'—',l:'templates'}),
        e(Kpi,{n:h?h.new_incident_types:'—',l:'new incidents'})),
      e('div',{className:'grid'},
        e('div',null,
          e('div',{className:'card'},e('h2',null,'New incident types (open-set clustering)'),
            inc.length?inc.map((c,i)=>e('div',{className:'row',key:c.id||i},
              e('span',{className:'pill'},'x'+c.members),
              e('div',{className:'grow'},e('div',null,c.label),
                e('div',{className:'mono'},c.sample_template)),
              e('span',{className:'sev'+c.max_severity},SEV[c.max_severity]||c.max_severity)
            )):e('div',{className:'muted'},'No new incident types — system nominal.')),
          e('div',{className:'card'},e('h2',null,'Top templates'),
            tpl.map((t,i)=>e('div',{className:'row',key:t.template_id||i},
              e('span',{className:'pill'},t.count),
              e('div',{className:'grow mono'},t.template),
              t.anomaly_count>0?e('span',{className:'sev4'},'!'+t.anomaly_count):null)))),
        e('div',null,
          e('div',{className:'card'},e('h2',null,'Severity distribution'),
            h?Object.entries(h.severity_hist).map(([s,c])=>{
              const tot=Object.values(h.severity_hist).reduce((a,b)=>a+b,0)||1;
              return e('div',{className:'row',key:s},
                e('div',{style:{width:52}},SEV[s]||s),
                e('div',{className:'grow bar'},e('i',{style:{width:(100*c/tot)+'%'}})),
                e('div',{className:'muted',style:{width:70,textAlign:'right'}},c.toLocaleString()));
            }):null),
          e('div',{className:'card'},e('h2',null,'Alerts routed'),
            al.length?al.map((a,i)=>e('div',{className:'row',key:a.id||i},
              e('span',{className:'chan'},(a.channels||[]).join('+')),
              e('div',{className:'grow mono'},a.title))):e('div',{className:'muted'},'No alerts.')))
      )
    )
  );
}
ReactDOM.createRoot(document.getElementById('root')).render(e(App));
</script>
</body>
</html>
"""
