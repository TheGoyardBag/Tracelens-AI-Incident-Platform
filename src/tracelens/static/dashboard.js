import {escapeHtml as e, percent, parseEvents, chartPoints} from './core.mjs';
const root=document.getElementById('app');
const state={token:sessionStorage.getItem('tracelens-token')||'',incidents:[],incident:null,run:null,events:[],evaluation:null,audit:[],tab:'diagnosis',page:'investigate',busy:false,mode:'offline',llmReady:false,error:''};
const brand='<div class="brand"><span class="brand-mark">⌁</span><span class="brand-name">TraceLens</span></div>';
let timer;
function toast(message){const node=document.getElementById('toast');node.textContent=message;node.style.display='block';clearTimeout(timer);timer=setTimeout(()=>node.style.display='none',5500);}
async function api(path,options={}){
 const response=await fetch(path,{...options,headers:{'Authorization':`Bearer ${state.token}`,'Content-Type':'application/json',...(options.headers||{})}});
 if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{detail=response.statusText;}throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));}
 return response.json();
}
function login(error=''){
 root.innerHTML=`<main class="login"><form id="login-form" class="login-box">${brand}<span class="badge">LOCAL WORKSPACE</span><h1>Follow the evidence.</h1><p class="subtle">A trained incident ranker, a transparent investigation, and every source one click away.</p><label for="token" class="subtle">Local API token</label><input id="token" type="password" name="token" autocomplete="off" placeholder="Paste the token from setup.py" required minlength="24"><button class="primary" type="submit">Open workspace →</button><p class="subtle">Generate a token with<br><code>python scripts/setup.py</code></p><p class="subtle">No paid API key is required for the offline evidence workflow. Included incidents are synthetic.</p>${error?`<p role="alert" style="color:var(--red)">${e(error)}</p>`:''}</form></main>`;
 document.getElementById('login-form').addEventListener('submit',async ev=>{ev.preventDefault();state.token=new FormData(ev.target).get('token').trim();try{await load();sessionStorage.setItem('tracelens-token',state.token);}catch(err){login(err.message);}});
}
async function load(){
 const [list,health,evaluation]=await Promise.all([api('/api/incidents'),fetch('/health').then(r=>r.json()),api('/api/evaluation').catch(()=>null)]);
 state.incidents=list.incidents;state.llmReady=health.llm_ready;state.evaluation=evaluation;
 if(state.incidents.length)await selectIncident(state.incidents[0].id);else render();
}
async function selectIncident(id){
 if(state.busy)return;
 state.incident=await api(`/api/incidents/${encodeURIComponent(id)}`);state.run=null;state.events=[];state.tab='diagnosis';render();
}
const chip=id=>`<button class="evidence-chip" data-evidence="${e(id)}">↗ ${e(id)}</button>`;
function chart(){
 const name=state.run?.result?.ranking.candidates[0]?.service||state.incident?.services[0]?.name;
 const service=state.incident?.services.find(s=>s.name===name);
 if(!service)return '';
 const vals=service.metrics.error_rate,points=chartPoints(vals);
 return `<div><div class="eyebrow">ERROR RATE · ${e(name)}</div><svg class="chart" viewBox="-5 -10 430 120" role="img" aria-label="Observed error rate for ${e(name)}"><line x1="0" y1="100" x2="420" y2="100" class="axis"/><line x1="0" y1="50" x2="420" y2="50" class="axis"/><polygon points="0,100 ${points} 420,100" class="plot-fill"/><polyline points="${points}" class="signal-line"/></svg><div class="chart-labels"><span>Window start</span><span>Peak ${percent(Math.max(...vals))}</span><span>Window end</span></div></div>`;
}
function ranks(){
 const items=state.run?.result?.ranking.candidates;
 if(!items)return `<div><div class="eyebrow">MODEL RANKING</div><p class="subtle" style="margin-top:20px">Run an investigation to compare candidate services. Scores are computed from the incident, not preset.</p></div>`;
 return `<div><div class="eyebrow">MODEL RANKING</div>${items.slice(0,5).map(s=>`<div class="rank"><span class="mono">${e(s.service)}</span><div class="rank-track"><div class="rank-fill" style="width:${s.probability*100}%"></div></div><span>${percent(s.probability)}</span></div>`).join('')}<div class="subtle" style="font-size:10px">Candidate-relative scores · synthetic calibration</div></div>`;
}
function diagnosis(){
 const result=state.run?.result;
 if(!result)return `<div class="empty"><div class="empty-icon ${state.busy?'spinning':''}">⌁</div><h3>${state.busy?'Collecting evidence…':'A hypothesis is only the beginning.'}</h3><p>${state.busy?'The workflow is ranking services and inspecting metrics, logs, traces, and changes.':'Start an investigation to rank likely causes and inspect the telemetry behind each finding.'}</p>${state.busy?`<span class="badge neutral">${state.events.filter(s=>s.kind==='tool').length} TOOL CALLS OBSERVED</span>`:'<button class="primary" data-action="run">Investigate this incident →</button>'}</div>`;
 const d=result.diagnosis;
 return `<div class="panel-body"><div class="detail-header"><div><div class="eyebrow">LEADING HYPOTHESIS</div><h2>${e(d.likely_service||'Insufficient evidence')}</h2></div><span class="badge ${d.status==='supported'?'good':''}">${e(d.status.toUpperCase())}</span></div><p class="summary">${e(d.summary)}</p><div class="eyebrow">SUPPORTING OBSERVATIONS</div>${d.claims.map(c=>`<article class="claim"><p>${e(c.text)}</p>${c.evidence_ids.map(chip).join('')}</article>`).join('')}<div class="eyebrow" style="margin-top:22px">NEXT STEPS · HUMAN REVIEW REQUIRED</div>${d.next_steps.map(s=>`<div class="next-step">${e(s)}</div>`).join('')}<details class="limitations"><summary>Boundaries, uncertainty & model limitations</summary>${d.limitations.map(l=>`<p>${e(l)}</p>`).join('')}<p>Mode: ${e(result.provider.effective_mode)}. Tool calls: ${result.tool_calls}. Investigation: ${(result.duration_ms/1000).toFixed(2)} s.</p></details></div><div class="feedback"><span>Help curate future evaluations</span><button class="ghost" data-action="correct">Looks right</button><button class="ghost" data-action="incorrect">Needs review</button><button class="secondary" data-action="review">Record human review</button></div>`;
}
function evidence(){
 const items=state.run?.result?.evidence||[];
 if(!items.length)return '<div class="empty">Evidence will appear after an investigation.</div>';
 return `<div class="panel-body"><div class="eyebrow">${items.length} RETRIEVED SOURCES · CLICK TO INSPECT</div>${items.map(item=>`<div class="evidence-card"><div><strong>${e(item.kind.toUpperCase())} · ${e(item.service||'Reference guidance')}</strong><p>${e(item.data.message||item.data.operation||item.data.title||item.id)}</p></div>${chip(item.id)}</div>`).join('')}</div>`;
}
function activity(){return `<div class="panel-body"><div class="eyebrow">EXECUTED WORKFLOW · NOT MODEL CHAIN OF THOUGHT</div>${state.events.length?state.events.map((s,i)=>`<div class="activity"><span class="activity-mark">${i+1}</span><div><div class="activity-name">${e(s.payload.tool||s.payload.message||s.kind)}</div><div class="activity-meta">${e(s.payload.arguments?JSON.stringify(s.payload.arguments):s.kind==='ranking'?'Candidate ranking computed':s.payload.citation_integrity||s.kind)}${s.payload.evidence_count!==undefined?` · ${s.payload.evidence_count} sources`:''}</div></div></div>`).join(''):'<p class="subtle">No investigation has run yet.</p>'}</div>`;}
function evaluation(){
 const v=state.evaluation;if(!v)return '<div class="panel"><div class="empty">Run the training command to generate reports.</div></div>';
 return `<div class="notice">${e(v.warning)} Test and challenge sets are not used for model selection. Both observations of an experiment stay in the same split.</div><div class="panel"><div class="panel-heading">Measured model comparison <span class="badge neutral">SEED ${v.seed}</span></div><div class="table-wrap"><table class="table"><thead><tr><th>Model</th><th>Test top-1</th><th>Test top-3</th><th>Challenge top-1</th><th>Test MRR</th></tr></thead><tbody>${Object.entries(v.results).map(([name,r])=>`<tr><td class="mono">${e(name)}</td><td class="best">${percent(r.test.top1)}</td><td>${percent(r.test.top3)}</td><td>${percent(r.challenge.top1)}</td><td>${r.test.mrr.toFixed(3)}</td></tr>`).join('')}</tbody></table></div><div class="panel-body"><div class="eyebrow">EVALUATION DESIGN</div><p class="subtle">Train: ${v.split_counts.train} · Validation: ${v.split_counts.validation} · Test: ${v.split_counts.test} · Challenge: ${v.split_counts.challenge}</p><p class="subtle">Challenge = held-out service/fault combinations, not unseen fault mechanisms. No-log and no-graph ablations are independently retrained. A simpler model may perform better.</p><p class="subtle">${e(v.confidence_interval)}</p><p class="subtle">No hosted LLM or production-incident accuracy has been measured.</p></div></div>`;
}
function audit(){return `<div class="panel"><div class="panel-heading">Workspace audit trail <span class="badge neutral">LOCAL RECORDS</span></div><div class="panel-body">${state.audit.map(a=>`<div class="activity"><span class="activity-mark">✓</span><div><div class="activity-name">${e(a.action)}</div><div class="activity-meta">${e(a.resource_id)} · ${e(a.created_at)}</div></div></div>`).join('')||'<p class="subtle">No records yet.</p>'}<p class="subtle">This is an application audit log, not tamper-proof compliance storage.</p></div></div>`;}
function workspace(){
 if(!state.incident)return '<div class="panel empty">No incidents yet. Import a normalized incident using the API.</div>';
 return `<div class="workspace"><aside class="panel"><div class="panel-heading">Incident replays <span class="subtle">${state.incidents.length}</span></div><div class="incident-list">${state.incidents.map(c=>`<button class="incident-item ${c.id===state.incident.id?'selected':''}" data-incident="${e(c.id)}" ${state.busy?'disabled':''}><span class="id">${e(c.id)}</span><strong>${e(c.title)}</strong><span class="badge small ${c.source==='synthetic'?'':'neutral'}">${e(c.source.toUpperCase())}</span></button>`).join('')}</div></aside><section class="detail"><div class="detail-header"><div><div class="eyebrow">SELECTED INCIDENT</div><h2>${e(state.incident.id)}</h2></div><span class="badge neutral">${state.run?.status?e(state.run.status.toUpperCase()):'READY TO INVESTIGATE'}</span></div><div class="panel"><div class="panel-body signal-grid">${chart()}${ranks()}</div></div><div class="panel"><div class="tabs">${['diagnosis','evidence','activity'].map(t=>`<button class="${state.tab===t?'active':''}" data-tab="${t}">${t.charAt(0).toUpperCase()+t.slice(1)}${t==='activity'&&state.events.length?` (${state.events.length})`:''}</button>`).join('')}</div>${state.tab==='diagnosis'?diagnosis():state.tab==='evidence'?evidence():activity()}</div></section></div>`;
}
function render(){
 const labels={investigate:['Incident workspace','Investigate before you intervene.'],evaluation:['Model evaluation','Measure the model. Question the result.'],audit:['Audit trail','Keep the decision trail visible.']};
 const [title,subtitle]=labels[state.page];
 root.innerHTML=`<div class="shell"><aside class="sidebar">${brand}<div class="eyebrow">WORKSPACE</div><nav class="nav" aria-label="Main navigation">${[['investigate','⌁','Investigations'],['evaluation','◫','Model evaluation'],['audit','≡','Audit trail']].map(([page,icon,label])=>`<button data-page="${page}" class="${state.page===page?'active':''}"><span class="symbol">${icon}</span>${label}</button>`).join('')}</nav><div class="sidebar-bottom"><div><span class="dot"></span>Local research workspace</div><p>Read-only by design.<br>No infrastructure changes.</p><button class="ghost" data-action="logout">Lock workspace</button></div></aside><main class="main"><header class="topbar"><span>Workspace / <span style="color:var(--text)">${title}</span></span><span class="badge">SYNTHETIC DEMO INCLUDED</span></header><div class="content"><section class="hero"><div><div class="eyebrow">OBSERVE / INVESTIGATE / VERIFY</div><h1>${title}</h1><p>${subtitle}</p></div>${state.page==='investigate'?`<div class="controls"><select aria-label="Investigation mode" id="mode-select" ${state.busy?'disabled':''}><option value="offline" ${state.mode==='offline'?'selected':''}>Offline evidence policy</option value="llm" ${state.mode==='llm'?'selected':''} ${state.llmReady?'':'disabled'}>Hosted LLM (opt-in)</option></select><button class="primary" data-action="run" ${state.busy?'disabled':''}>${state.busy?'Investigating…':'New investigation →'}</button></div>`:''}</section><section class="stats"><div class="stat"><div class="stat-label">SERVICES IN VIEW</div><div class="stat-value">${state.incident?.services.length||0}</div><div class="subtle">Metrics, logs & dependency traces</div></div><div class="stat"><div class="stat-label">HELD-OUT TEST OBSERVATIONS</div><div class="stat-value">${state.evaluation?.split_counts.test||'—'}</div><div class="subtle">Grouped by independent experiment</div></div><div class="stat"><div class="stat-label">INVESTIGATION BOUNDARY</div><div class="stat-value" style="font-size:22px">${state.mode==='offline'?'Local only':'Explicit opt-in'}</div><div class="subtle">${state.mode==='offline'?'No model API key or telemetry export':'Selected excerpts may leave your machine'}</div></div></section>${state.page==='investigate'?workspace():state.page==='evaluation'?evaluation():audit()}<p class="footer-note">TraceLens v0.1 · Synthetic calibration is not production assurance. Every recommendation requires human judgment.</p></div></main></div>`;
 document.getElementById('mode-select')?.addEventListener('change',ev=>{state.mode=ev.target.value;render();});
}
async function runInvestigation(){
 if(state.busy||!state.incident)return;
 state.busy=true;state.run=null;state.events=[];state.tab='diagnosis';render();
 try{
  const run=await api('/api/runs',{method:'POST',body:JSON.stringify({incident_id:state.incident.id,mode:state.mode,idempotency_key:crypto.randomUUID()})});state.run=run;render();
  const response=await fetch(`/api/runs/${run.id}/events`,{headers:{Authorization:`Bearer ${state.token}`}});
  if(!response.ok||!response.body)throw new Error('Event stream unavailable; see saved run history in the API.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const parsed=parseEvents(buffer);buffer=parsed.rest;for(const event of parsed.events){if(event.name==='step')state.events.push(event.data);}render();}
  state.run=await api(`/api/runs/${run.id}`);
  if(state.run.status!=='complete')throw new Error(state.run.error||`Investigation ${state.run.status}`);
 }catch(err){toast(err.message);}finally{state.busy=false;render();}
}
function showEvidence(id){const item=state.run?.result?.evidence.find(v=>v.id===id);if(!item)return;const el=document.getElementById('evidence-dialog');el.hidden=false;el.innerHTML=`<section class="dialog" role="dialog" aria-modal="true" aria-label="Retrieved evidence"><header><h3>${e(item.id)}</h3><button class="ghost" data-close-dialog>Close ×</button></header><pre>${e(JSON.stringify(item.data,null,2))}</pre></section>`;el.querySelector('button').focus();}
document.addEventListener('keydown',ev=>{if(ev.key==='Escape')document.getElementById('evidence-dialog').hidden=true;});
document.getElementById('evidence-dialog').addEventListener('click',ev=>{if(ev.target.id==='evidence-dialog'||ev.target.closest('[data-close-dialog]'))document.getElementById('evidence-dialog').hidden=true;});
root.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button)return;
 try{
 if(button.dataset.incident)await selectIncident(button.dataset.incident);
 else if(button.dataset.tab){state.tab=button.dataset.tab;render();}
 else if(button.dataset.evidence)showEvidence(button.dataset.evidence);
 else if(button.dataset.page){state.page=button.dataset.page;if(state.page==='audit')state.audit=(await api('/api/audit')).events;render();}
 else if(button.dataset.action==='run')await runInvestigation();
 else if(button.dataset.action==='logout'){sessionStorage.removeItem('tracelens-token');state.token='';login();}
 else if(['correct','incorrect'].includes(button.dataset.action)&&state.run){await api(`/api/runs/${state.run.id}/feedback`,{method:'POST',body:JSON.stringify({correct:button.dataset.action==='correct',note:'Recorded in local workspace'})});toast('Feedback saved for manual curation. The model has not been retrained.');}
 else if(button.dataset.action==='review'&&state.run){const note=prompt('Record your review note. This DOES NOT execute remediation.');if(note?.trim()){await api(`/api/runs/${state.run.id}/review`,{method:'POST',body:JSON.stringify({confirmed:true,note:note.trim()})});toast('Human review recorded. No infrastructure changes were made.');}}
 }catch(err){toast(err.message);}
});
if(state.token)load().catch(err=>login(err.message));else login();
