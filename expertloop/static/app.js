'use strict';

const state = {dashboard: null, tasks: [], task: null, run: null, view: 'overview',
  split: 'development', category: '', search: '', status: '', fixture: 'standard',
  evaluation: null, expandedResult: null, poll: null, token: 0};
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
const pp = value => value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}`;
const shortId = id => esc(id?.slice(-8) || '');
const labels = {join_cardinality:'Join cardinality', aggregation:'Aggregation', date_boundaries:'Date boundaries', missing_values:'Missing values', business_rules:'Business rules', ranking:'Ranking & ties'};
const symbols = {join_cardinality:'⋈', aggregation:'Σ', date_boundaries:'◷', missing_values:'∅', business_rules:'≡', ranking:'↕'};
const titles = {overview:'Overview', dataset:'Task library', review:'Human review', experiments:'Experiments', guide:'Build notes'};

async function api(path, body) {
  const options = body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-ExpertLoop':'1'}, body:JSON.stringify(body)};
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail); } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}
let toastTimer;
function toast(message, error = false) {
  const el = $('#toast');
  el.textContent = message;
  el.className = `show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 5500);
}
function statusPill(status) {
  const style = {approved:'green',pending:'amber',rejected:'red',locked:'gray',completed:'green',running:'green',queued:'amber',paused:'amber',failed:'red'}[status] || 'gray';
  return `<span class="pill ${style}">${esc(status === 'locked' ? 'Holdout · locked' : status)}</span>`;
}
function categoryTag(category) { return `<span class="category-tag">${esc(labels[category] || category)}</span>`; }
function heading(eyebrow, title, subtitle, action = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="muted">${esc(subtitle)}</p></div>${action}</div>`;
}
function stat(label, value, note, featured = false, icon = '↗') {
  return `<div class="stat-card${featured?' featured':''}"><div class="stat-top"><span>${esc(label)}</span><span>${icon}</span></div><div class="stat-value">${esc(value)}</div><div class="stat-bottom">${note}</div></div>`;
}
function prettySQL(sql) {
  return esc(sql.replace(/\s+(FROM|WHERE|LEFT JOIN|JOIN|GROUP BY|ORDER BY|LIMIT|HAVING)\b/g, '\n$1'))
    .replace(/\b(SELECT|FROM|WHERE|LEFT|JOIN|ON|AS|AND|OR|NOT|NULL|GROUP|BY|ORDER|DESC|ASC|LIMIT|WITH|SUM|COUNT|AVG|COALESCE|CASE|WHEN|THEN|ELSE|END|DISTINCT|EXISTS)\b/g, '<b>$1</b>');
}
function runRows(runs) {
  return runs.map(r => `<a class="run-row" href="#experiments:${esc(r.id)}"><div class="run-symbol">⌁</div><div class="run-name">${esc(r.config.name)}<small>${esc(r.config.provider === 'demo' ? 'SCRIPTED DEMO' : r.config.model)} · ${r.task_count} tasks · ${r.example_count} examples</small></div>${statusPill(r.status)}<div class="run-metric">${pct(r.summary.improved_accuracy)}<small>example arm</small></div><span class="arrow-link">↗</span></a>`).join('');
}

function renderOverview(d) {
  const c = d.counts;
  const latest = d.runs[0];
  const approvedCategories = d.categories.filter(x => x.approved > 0).length;
  const scriptApprovals = d.activity.some(a => a.reviewer === 'SCRIPTED_DEMO_NOT_HUMAN');
  return `${heading('EXPERTISE, MADE MEASURABLE', 'Your intelligence workbench.', 'Turn human corrections into verified data and reproducible evidence.', '<button class="button primary" data-action="new-run">New experiment <span>↗</span></button>')}
    ${scriptApprovals ? '<div class="notice warning"><strong>Scripted sample workspace.</strong> Demo approvals were made by automation, not a human expert. Start a fresh workspace for real reviews.</div>' : ''}
    <section class="hero"><div><div class="eyebrow">CLOSE THE LOOP</div><h2>Better models start<br>with better judgment.</h2><p>Capture a correction. Verify it on real SQL results.<br>Measure whether it carries over to unseen tasks.</p></div><div class="hero-flow"><div class="flow-step"><div class="flow-icon">✎</div><b>Human review</b><small>Capture expertise</small></div><span class="flow-arrow">→</span><div class="flow-step"><div class="flow-icon">▦</div><b>Verified data</b><small>Keep the provenance</small></div><span class="flow-arrow">→</span><div class="flow-step"><div class="flow-icon">⌁</div><b>Paired evaluation</b><small>Measure the change</small></div></div></section>
    <div class="stats-grid">${stat('Development tasks', c.development, `${c.synthetic} generated variants · ${c.development-c.synthetic} seeds`, false, '▦')}${stat('Approved examples',c.approved,`${c.pending} awaiting review`,true,'✓')}${stat('Held-out tasks',c.holdout,'10 separate template families',false,'◇')}${stat('Execution fixtures',c.fixtures,'Standard · edge cases · sparse',false,'⌘')}</div>
    <div class="grid-two"><section class="panel"><div class="panel-head"><div><h3>Expertise coverage</h3><p>Approved development examples by failure category</p></div><span class="pill quiet">${approvedCategories} / 6 categories</span></div><div class="panel-body">${d.categories.map(cat => `<div class="coverage-row"><div class="coverage-symbol">${symbols[cat.id]}</div><span class="coverage-label">${esc(cat.label)}</span><div class="coverage-track"><span style="width:${100*cat.approved/Math.max(1,cat.development)}%"></span></div><span class="coverage-count"><b>${cat.approved}</b> / ${cat.development}</span></div>`).join('')}</div><div class="panel-foot">Coverage is not quality. Every approval still needs human judgment.</div></section>
    <section class="panel"><div class="panel-head"><div><h3>Your next steps</h3><p>A small workflow with an end-to-end story</p></div><span class="pill quiet">START HERE</span></div><div class="panel-body"><div class="steps"><a class="step ${c.approved?'done':''}" href="#review"><div class="step-num">${c.approved?'✓':'01'}</div><div><h4>Review a failed answer</h4><p>Correct the SQL and explain what went wrong.</p></div></a><button class="step text-link ${c.synthetic?'done':''}" data-action="generate" style="text-align:left"><span class="step-num">${c.synthetic?'✓':'02'}</span><span><h4>Generate related tasks</h4><p>48 template-backed variants, all pending review.</p></span></button><button class="step text-link ${latest?.status==='completed'?'done':''}" data-action="new-run" style="text-align:left"><span class="step-num">${latest?.status==='completed'?'✓':'03'}</span><span><h4>Run a paired comparison</h4><p>Same model. Same tasks. With and without examples.</p></span></button></div></div><div class="panel-foot">Demo mode runs locally. Live mode requires an API key.</div></section></div>
    <div class="section-heading"><h3>Recent experiments</h3><a class="text-link" href="#experiments">View all experiments ↗</a></div><section class="panel">${d.runs.length ? runRows(d.runs.slice(0,3)) : '<div class="empty-state"><div class="empty-symbol">⌁</div><h3>Your first experiment starts with one correction.</h3><p>Approve an example in Human review, then compare both configurations on the holdout.</p><a class="button secondary small" href="#review">Open review queue →</a></div>'}</section>`;
}

function renderDataset() {
  const tasks = state.tasks.filter(t => t.split === state.split && (!state.category || t.category === state.category) && (!state.status || t.review_status === state.status) && (!state.search || `${t.question} ${t.id} ${t.category}`.toLowerCase().includes(state.search.toLowerCase())));
  return `${heading('THE DATA LAYER','Task library.','Every question has a source, an executable reference, and a review state.', '<div class="button-row"><a class="button secondary" href="/api/export?format=provenance">Export approved ↓</a><button class="button primary" data-action="generate">Generate variants <span>＋</span></button></div>')}
    <div class="toolbar"><div class="tabs"><button class="tab ${state.split==='development'?'selected':''}" data-action="split" data-split="development">Development <span class="mono">${state.dashboard.counts.development}</span></button><button class="tab ${state.split==='holdout'?'selected':''}" data-action="split" data-split="holdout">Holdout <span class="mono">30</span></button></div><div class="filter-controls"><input id="task-search" class="search" aria-label="Search tasks" placeholder="Search questions or IDs…" value="${esc(state.search)}"><select id="category-filter" aria-label="Filter category"><option value="">All categories</option>${Object.entries(labels).map(([k,v])=>`<option value="${k}" ${state.category===k?'selected':''}>${esc(v)}</option>`).join('')}</select><select id="status-filter" aria-label="Filter review state"><option value="">All states</option>${['pending','approved','rejected'].map(v=>`<option ${state.status===v?'selected':''}>${v}</option>`).join('')}</select></div></div>
    <div class="notice ${state.split==='holdout'?'warning':''}">${state.split==='holdout'?'<strong>Evaluation only.</strong> These task families never enter the generator, review approvals, or training export. Inspecting results repeatedly can still lead to overfitting.':'<strong>Mechanically verified ≠ human-approved.</strong> References are template-derived and checked on three fixtures. Generated variants remain pending until a reviewer approves them.'}</div>
    <section class="panel"><div class="table-wrap"><table class="task-table"><thead><tr><th>TASK / PROVENANCE</th><th>BUSINESS QUESTION</th><th>FAILURE CATEGORY</th><th>REVIEW STATE</th><th></th></tr></thead><tbody>${tasks.map(t=>`<tr data-task-link="${esc(t.id)}" tabindex="0" role="link" aria-label="Inspect task ${esc(t.id)}"><td class="nowrap"><span class="mono table-id">${shortId(t.id)}</span><div class="micro">${t.parent_id?'Synthetic variant':'Authored template'}</div></td><td class="task-question">${esc(t.question)}<small>${esc(t.family)}</small></td><td>${categoryTag(t.category)}</td><td>${statusPill(t.review_status)}</td><td class="arrow-link">↗</td></tr>`).join('') || '<tr><td colspan="5"><div class="empty-state">No tasks match these filters.</div></td></tr>'}</tbody></table></div><div class="panel-foot">${tasks.length} tasks · exact duplicate IDs are deduplicated · monetary values are USD cents</div></section>`;
}

function tableHTML(result) {
  if (!result?.ok) return `<div class="notice danger">${esc(result?.error || 'No output')}</div>`;
  const rows = result.rows.slice(0,8);
  return `<div class="table-wrap"><table><thead><tr>${result.columns.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${v===null?'<span class="muted">NULL</span>':esc(v)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${Math.max(1,result.columns.length)}" class="muted">No rows</td></tr>`}</tbody></table></div>${result.rows.length>8?`<div class="micro">Showing 8 of ${result.rows.length} rows.</div>`:''}`;
}
function evaluationHTML(evaluation) {
  if (!evaluation) return '';
  const names = Object.keys(evaluation.fixtures);
  const selected = names.includes(state.fixture) ? state.fixture : names[0];
  const check = evaluation.fixtures[selected];
  return `<section class="panel"><div class="panel-head"><div><h3>Execution evidence</h3><p>Pass requires matching every fixture</p></div><div class="fixture-tabs">${names.map(name=>`<button class="fixture-tab ${name===selected?'active':''}" data-action="fixture" data-fixture="${name}"><span class="${evaluation.fixtures[name].passed?'check-pass':'check-fail'}">${evaluation.fixtures[name].passed?'✓':'×'}</span> ${esc(name.replaceAll('_',' '))}</button>`).join('')}</div></div><div class="panel-body"><div class="result-tables"><div><div class="result-table-label">EXPECTED RESULT</div>${tableHTML(check.expected)}</div><div><div class="result-table-label">ACTUAL RESULT</div>${tableHTML(check.actual)}</div></div><p class="evaluation-reason"><span class="${check.passed?'check-pass':'check-fail'}">${check.passed?'✓':'×'}</span> ${esc(check.reason)}</p></div></section>`;
}
function renderReview() {
  const data = state.task;
  if (!data) return '<div class="empty-state">No tasks available.</div>';
  const t = data.task;
  const locked = t.split === 'holdout';
  const queue = state.tasks.filter(x => x.split === (locked?'holdout':'development'));
  const corrected = t.corrected_sql || data.candidate_sql;
  return `${heading(locked?'HOLDOUT INSPECTOR':'HUMAN JUDGMENT, CAPTURED',locked?'Inspect the evidence.':'Review. Correct. Verify.',locked?'Read-only evaluation tasks. Never approve these as development examples.':'A correction becomes useful only when its provenance and quality are preserved.', '<button class="button secondary" data-action="next-task">Next pending task →</button>')}
    <div class="review-layout"><aside class="panel queue"><div class="queue-head"><span>${locked?'Holdout tasks':'Development queue'}</span><span class="pill quiet">${queue.length}</span></div><div class="queue-list">${queue.map(x=>`<button class="queue-item ${x.id===t.id?'selected':''}" data-action="open-task" data-id="${esc(x.id)}">${categoryTag(x.category)}<strong>${esc(x.question)}</strong><small>${shortId(x.id)} · ${esc(x.review_status)}</small></button>`).join('')}</div></aside><div class="review-main">
    <section class="review-question"><div class="review-meta">${categoryTag(t.category)}${statusPill(t.review_status)}<span class="mono">${esc(t.id)}</span><span>revision ${t.revision}</span></div><h2>${esc(t.question)}</h2><div class="micro">${esc(data.candidate_origin)} · ${t.ordered?'Row order matters':'Row order is ignored; duplicates matter'}</div></section>
    ${locked?'<div class="notice warning"><strong>Holdout boundary.</strong> Corrections and approvals are disabled. Do not tune prompts against these answers and call the same set unseen.</div>':''}
    <div class="review-editors"><div class="code-panel"><div class="code-title"><span>Original candidate</span><span class="pill ${data.evaluation.passed?'green':'red'}">${data.evaluation.passed?'passes suite':'fails suite'}</span></div><pre>${prettySQL(data.candidate_sql)}</pre></div><div class="code-panel"><div class="code-title"><span>${locked?'Reference SQL':'Your corrected SQL'}</span>${locked?'<span class="pill quiet">LOCKED</span>':'<button class="text-link" data-action="use-reference">Use reference ↙</button>'}</div>${locked?`<pre>${prettySQL(t.reference_sql)}</pre>`:`<textarea id="sql-editor" class="sql-editor" aria-label="Corrected SQL" spellcheck="false">${esc(corrected)}</textarea>`}</div></div>
    <div id="evaluation-container">${evaluationHTML(state.evaluation || data.evaluation)}</div>
    ${locked?'':`<section class="panel review-form"><div class="form-grid"><label>Reviewer name<input id="reviewer-name" placeholder="Your name" maxlength="80" value="${esc(localStorage.getItem('expertloop-reviewer') || '')}"></label><label>What changed, and why?<textarea id="review-note" placeholder="For example: joining order lines repeated each order total." maxlength="2000">${esc(t.review_note)}</textarea></label></div><div class="button-row"><button class="button secondary" data-action="validate">Validate on 3 fixtures</button><button class="button accent" data-action="approve">Approve correction ✓</button><button class="button ghost" data-action="reject">Reject task</button>${t.review_status!=='pending'?'<button class="button ghost" data-action="pending">Reopen</button>':''}</div><div class="micro" style="margin-top:12px">Approval re-runs validation server-side. It never overwrites the original candidate or reference.</div><details><summary>Reference SQL & business rules</summary><pre>${esc(t.reference_sql)}</pre><pre>${esc(state.dashboard.rules)}</pre></details></section>`}
    ${data.reviews.length?`<section class="panel" style="margin-top:17px"><div class="panel-head"><h3>Review history</h3><span class="pill quiet">APPEND-ONLY</span></div><div class="panel-body">${data.reviews.map(r=>`<div class="audit-row">${statusPill(r.action)}<div><p>${esc(r.note)}</p><small>${esc(r.reviewer)} · ${esc(r.created_at)} · revision ${r.previous_revision+1}</small></div></div>`).join('')}</div></section>`:''}
    </div></div>`;
}

function renderExperiments(d, run) {
  const startButton = '<button class="button primary" data-action="new-run">New experiment <span>↗</span></button>';
  if (!run) return `${heading('FROM CORRECTION TO EVIDENCE','Experiments.','Compare baseline and approved-example configurations on the same tasks.',startButton)}<section class="panel"><div class="empty-state"><div class="empty-symbol">⌁</div><h3>No experiments yet.</h3><p>Approve at least one development example, then run the paired evaluation. Demo mode exercises the pipeline without making API calls.</p><button class="button primary" data-action="new-run">Create first experiment ↗</button></div></section>`;
  const s = run.summary;
  const active = ['running','queued'].includes(run.status);
  const ci = s.ci95 ? `95% interval [${pp(s.ci95[0])}, ${pp(s.ci95[1])}] pp` : 'Interval not yet available';
  const index = Object.fromEntries(run.results.map(r=>[`${r.task_id}:${r.arm}`,r]));
  const expanded = run.tasks.find(t=>t.id===state.expandedResult);
  return `${heading('FROM CORRECTION TO EVIDENCE','Experiments.','Same tasks. Paired outcomes. An honest account of what changed.',startButton)}
    <div class="toolbar"><select class="run-select" id="run-select" aria-label="Choose experiment">${d.runs.map(r=>`<option value="${r.id}" ${r.id===run.id?'selected':''}>${esc(r.config.name)} · ${r.id.slice(-6)}</option>`).join('')}</select><div class="button-row"><a class="button secondary small" href="/api/runs/${run.id}/report">Report ↓</a><a class="button secondary small" href="/api/runs/${run.id}/artifact">Full artifact ↓</a></div></div>
    <div class="notice ${run.config.provider==='demo'?'warning':''}"><strong>${run.config.provider==='demo'?'SCRIPTED DEMO — NOT MODEL EVIDENCE.':'LIVE MODEL EXPERIMENT.'}</strong> ${run.config.provider==='demo'?'Outputs use programmed mistakes and reference answers to exercise the pipeline. Any apparent improvement is simulated.':'Few-shot prompting, not fine-tuning. This is a small synthetic benchmark, not a claim about broad professional capability.'}</div>
    <div class="run-progress"><div class="run-header"><div><h3>${esc(run.config.name)}</h3><p class="micro">${esc(run.config.model)} · ${run.config.split} · ${run.example_count} fixed examples</p></div><div class="button-row">${statusPill(run.status)}${active?'<button class="button secondary small" data-action="pause-run">Pause run</button>':run.status!=='completed'?'<button class="button secondary small" data-action="resume-run">Resume remaining tasks</button>':''}</div></div><div class="progress-track"><span style="width:${100*run.completed_results/Math.max(1,run.total_results)}%"></span></div><div class="micro">${run.completed_results} / ${run.total_results} outputs persisted · ${run.request_count} / ${run.max_requests} attempted requests${active?' · in-flight calls may finish after pause':''}</div>${run.error?`<div class="notice danger" style="margin-top:10px">${esc(run.error)}</div>`:''}</div>
    <div class="stats-grid experiment-metrics">${stat('Baseline accuracy',pct(s.baseline_accuracy),'Passes across all three fixtures')}${stat('With approved examples',pct(s.improved_accuracy),'Same model, different context',true)}${stat('Paired difference',s.delta==null?'—':`${pp(s.delta)} pp`,esc(ci))}${stat('Completed task pairs',`${s.n} / ${s.total_tasks}`,`${s.families} template families`,false,'◇')}</div>
    <div class="grid-two"><section class="panel"><div class="panel-head"><div><h3>Performance by failure category</h3><p>Execution accuracy on completed task pairs</p></div><div class="chart-legend"><span><i class="legend-dot"></i>Baseline</span><span><i class="legend-dot improved"></i>Examples</span></div></div><div class="panel-body">${s.categories.map(cat=>`<div class="category-chart-row"><div class="chart-row-title"><span>${esc(labels[cat.category])}</span><small>n = ${cat.n}</small></div><div class="bar-pair"><div class="bar-line"><div class="bar-track"><span style="width:${cat.baseline*100}%"></span></div><small>${Math.round(cat.baseline*100)}%</small></div><div class="bar-line improved"><div class="bar-track"><span style="width:${cat.improved*100}%"></span></div><small>${Math.round(cat.improved*100)}%</small></div></div></div>`).join('') || '<p class="muted">Results will appear as paired tasks finish.</p>'}</div><div class="panel-foot">Family-cluster paired bootstrap · 5,000 resamples · seed 7 · preliminary uncertainty</div></section>
    <section class="panel"><div class="panel-head"><div><h3>Experiment provenance</h3><p>Frozen at creation, retained on resume</p></div><span class="pill quiet">VERSIONED</span></div><div class="panel-body"><div class="provenance-list"><div><small>DATASET SNAPSHOT</small><code>${esc(run.dataset_hash.slice(0,24))}…</code></div><div><small>PROMPT / EVALUATOR</small><span class="mono">${esc(run.prompt_version)} / ${esc(run.evaluator_version)}</span></div><div><small>APPROVED EXAMPLE SNAPSHOT</small><code>${esc(run.example_hash.slice(0,24))}…</code></div><div><small>ACTUAL MODEL USAGE</small><span>${run.config.provider==='demo'?'No API calls. Tokens and model latency are not simulated.':`${((s.arms.baseline?.input_tokens||0)+(s.arms.improved?.input_tokens||0)).toLocaleString()} input / ${((s.arms.baseline?.output_tokens||0)+(s.arms.improved?.output_tokens||0)).toLocaleString()} output tokens on paired results`}</span></div></div><div class="mini-metrics"><div><strong>${s.wins}</strong><small>improved</small></div><div><strong>${s.regressions}</strong><small>regressed</small></div><div><strong>${s.unchanged}</strong><small>unchanged</small></div></div><p class="micro" style="margin:0">A passing fixture suite is evidence, not proof of semantic equivalence. Keep final evaluation independent of prompt selection.</p></div></section></div>
    <section class="panel"><div class="panel-head"><div><h3>Task-level outcomes</h3><p>Inspect the outputs, not just the aggregate score</p></div><span class="pill quiet">${run.tasks.length} TASKS</span></div><div class="table-wrap"><table class="task-table"><thead><tr><th>QUESTION</th><th>CATEGORY</th><th>BASELINE</th><th>EXAMPLES</th><th></th></tr></thead><tbody>${run.tasks.map(t=>{const a=index[`${t.id}:baseline`],b=index[`${t.id}:improved`];return `<tr data-result-link="${t.id}" tabindex="0" role="button"><td class="task-question">${esc(t.question)}<small>${esc(t.id)}</small></td><td>${categoryTag(t.category)}</td><td class="${a?.evaluation.passed?'check-pass':'check-fail'}">${a?(a.error?'error':a.evaluation.passed?'✓ pass':'× fail'):'—'}</td><td class="${b?.evaluation.passed?'check-pass':'check-fail'}">${b?(b.error?'error':b.evaluation.passed?'✓ pass':'× fail'):'—'}</td><td class="arrow-link">↙</td></tr>`;}).join('')}</tbody></table></div></section>
    ${expanded?`<section class="panel result-detail" id="result-detail"><div class="panel-head"><div><h3>Output inspector</h3><p>${esc(expanded.question)}</p></div><button class="text-link" data-action="close-result">Close ×</button></div><div class="review-editors">${['baseline','improved'].map(arm=>{const r=index[`${expanded.id}:${arm}`];return `<div class="code-panel"><div class="code-title">${arm==='baseline'?'Baseline':'With examples'}<span class="pill ${r?.evaluation.passed?'green':'red'}">${r?(r.evaluation.passed?'pass':'fail'):'pending'}</span></div><pre>${prettySQL(r?.sql || r?.error || 'No output yet')}</pre></div>`;}).join('')}</div><div class="panel-body">${evaluationHTML(index[`${expanded.id}:improved`]?.evaluation || index[`${expanded.id}:baseline`]?.evaluation)}</div></section>`:''}`;
}

function renderGuide(d) {
  return `${heading('BUILT TO BE EXPLAINED','Under the hood.','A small applied-AI system with explicit boundaries and inspectable evidence.')}
    <div class="guide-grid"><section class="panel"><div class="panel-head"><h3>The architecture</h3><span class="pill quiet">ONE SERVICE</span></div><div class="panel-body"><pre>Browser UI\n    ↓\nFastAPI · local write guard\n    ├── SQLite metadata & review audit\n    ├── Deterministic task generator\n    └── Resumable evaluation coordinator\n            ├── Scripted demo / live API\n            ├── Restricted SQL subprocess\n            └── Paired statistics & exports</pre><p>There is no frontend build step, external database, vector store, or orchestration framework. The first version prioritizes a working, testable loop.</p><a class="button secondary small" href="/docs" target="_blank" rel="noopener">Explore API documentation ↗</a></div></section>
    <section class="panel"><div class="panel-head"><h3>What this does — and does not — show</h3></div><div class="panel-body"><h4>Applied AI engineering</h4><p>Human review, synthetic task variants, quality gates, inference integration, persistent run snapshots, bounded concurrency, request caps, pause/resume, and paired evaluation.</p><h4>Not included</h4><p>Fine-tuning, independent domain-expert certification, a large representative benchmark, multi-tenant authentication, or a production-grade execution sandbox.</p><div class="notice warning">Scripted demo improvements are programmed behavior, not measured model learning. Live mode compares few-shot prompting, not updated model weights.</div></div></section>
    <section class="panel"><div class="panel-head"><h3>Data contract</h3><span class="pill quiet">SQLITE</span></div><div class="panel-body"><pre>${esc(d.schema)}</pre><details><summary>Read all business rules</summary><pre>${esc(d.rules)}</pre></details><p class="micro" style="margin-top:15px">Fixtures include guest orders, missing countries, unsold products, zero-value purchases, date boundaries, and repeated order totals.</p></div></section>
    <section class="panel"><div class="panel-head"><h3>Your interview demo</h3></div><div class="panel-body"><h4>1. Show a concrete failure</h4><p>Open the monthly revenue seed. A join repeats each order total for every line item. Compare expected and actual results.</p><h4>2. Capture a correction</h4><p>Fix the SQL, add your explanation, validate all three fixtures, and approve the example. Show its revision history.</p><h4>3. Show the experiment</h4><p>Run a paired holdout comparison. Explain the fixed example snapshot, family-level bootstrap, regressions, and limitations.</p><h4>4. Replace simulation with evidence</h4><p>Set a server-side API key and supported model, collect genuine reviews, run a live comparison, and report what actually happens — even if improvement is zero.</p><a class="button secondary small" href="/api/export?format=sft">Export approved SFT-format data ↓</a></div></section></div>`;
}

async function route() {
  const token = ++state.token;
  clearTimeout(state.poll);
  const [requested='overview', id] = location.hash.slice(1).split(':');
  state.view = titles[requested] ? requested : 'overview';
  $('#breadcrumb').textContent = titles[state.view];
  document.querySelectorAll('[data-nav]').forEach(el => el.classList.toggle('active',el.dataset.nav===state.view));
  try {
    const d = await api('/dashboard');
    if (token !== state.token) return;
    state.dashboard = d;
    $('#task-badge').textContent = d.counts.development + d.counts.holdout;
    $('#review-badge').textContent = d.counts.pending;
    if (state.view==='overview') $('#content').innerHTML = renderOverview(d);
    else if (state.view==='dataset') {
      state.tasks = await api('/tasks');
      if (token === state.token) $('#content').innerHTML = renderDataset();
    } else if (state.view==='review') {
      state.tasks = await api('/tasks');
      const selected = id || state.tasks.find(t=>t.split==='development' && t.review_status==='pending')?.id || state.tasks[0]?.id;
      state.task = selected ? await api(`/tasks/${encodeURIComponent(selected)}`) : null;
      state.evaluation = null;
      state.fixture = 'standard';
      if (token === state.token) $('#content').innerHTML = renderReview();
    } else if (state.view==='experiments') {
      const selected = id || d.runs[0]?.id;
      state.run = selected ? await api(`/runs/${encodeURIComponent(selected)}`) : null;
      if (token === state.token) {
        $('#content').innerHTML = renderExperiments(d,state.run);
        schedulePoll();
      }
    } else if (state.view==='guide') $('#content').innerHTML = renderGuide(d);
  } catch (error) {
    if (token===state.token) $('#content').innerHTML = `<section class="panel empty-state"><h3>Could not open this view.</h3><p>${esc(error.message)}</p><button class="button secondary" data-action="refresh">Try again</button></section>`;
  }
}
function schedulePoll() {
  clearTimeout(state.poll);
  if (state.view==='experiments' && state.run && ['queued','running'].includes(state.run.status)) {
    state.poll = setTimeout(async()=>{
      try {
        const run = await api(`/runs/${state.run.id}`);
        if (state.view!=='experiments' || run.id!==state.run.id) return;
        state.run=run;
        $('#content').innerHTML=renderExperiments(state.dashboard,run);
        schedulePoll();
      } catch(error) {toast(error.message,true);}
    },1500);
  }
}
function openRunDialog() {
  const d = state.dashboard;
  $('#model-input').value = d.default_model;
  $('#provider-select').value='demo';
  $('#provider-select option[value="openai"]').disabled = !d.live_available;
  providerNote();
  $('#run-dialog').showModal();
}
function providerNote() {
  const live = $('#provider-select').value==='openai';
  $('#model-label').hidden=!live;
  $('#model-input').required=live;
  $('#provider-note').className=`notice${live?' warning':''}`;
  $('#provider-note').textContent=live?
    'Live mode sends the fictional schema, question, and approved examples to OpenAI. Requests may incur charges. The API key stays on the server.':
    `Scripted demo: no API calls and no real model improvement. ${state.dashboard.counts.approved} approved examples are available. Without examples, both arms receive the same context.`;
}

async function handleAction(action, element) {
  if(action==='new-run') return openRunDialog();
  if(action==='close-dialog') return $('#run-dialog').close();
  if(action==='refresh') return route();
  if(action==='open-task') {location.hash=`review:${element.dataset.id}`;return;}
  if(action==='split') {state.split=element.dataset.split;state.status='';$('#content').innerHTML=renderDataset();return;}
  if(action==='use-reference') {$('#sql-editor').value=state.task.task.reference_sql;toast('Reference inserted. Review it and explain the correction before approval.');return;}
  if(action==='fixture') {
    state.fixture=element.dataset.fixture;
    if(state.view==='review') $('#evaluation-container').innerHTML=evaluationHTML(state.evaluation||state.task.evaluation);
    else {const y=window.scrollY;$('#content').innerHTML=renderExperiments(state.dashboard,state.run);window.scrollTo(0,y);}
    return;
  }
  if(action==='close-result') {state.expandedResult=null;$('#content').innerHTML=renderExperiments(state.dashboard,state.run);return;}
  if(action==='next-task') {
    const tasks=await api('/tasks?split=development&status=pending');
    const next=tasks.find(t=>t.id!==state.task?.task.id)||tasks[0];
    if(next) location.hash=`review:${next.id}`; else toast('No pending development tasks. Generate variants to add more.');
    return;
  }
  element.disabled=true;
  try {
    if(action==='generate') {
      const batch=await api('/generate',{});
      toast(batch.inserted?`${batch.inserted} verified variants added. All are pending human review.`:'No new variants: all 48 already exist. Duplicates were skipped.');
      await route();
    } else if(action==='validate') {
      state.evaluation=await api(`/tasks/${state.task.task.id}/validate`,{sql:$('#sql-editor').value});
      $('#evaluation-container').innerHTML=evaluationHTML(state.evaluation);
      toast(state.evaluation.passed?'Matches all three fixtures. Review the semantics before approving.':'One or more fixtures failed. Inspect the result differences.',!state.evaluation.passed);
    } else if(['approve','reject','pending'].includes(action)) {
      const reviewer=$('#reviewer-name').value.trim();
      const note=$('#review-note').value.trim();
      if(!reviewer||note.length<3) throw new Error('Enter your name and a short review explanation.');
      const decision={approve:'approved',reject:'rejected',pending:'pending'}[action];
      await api(`/tasks/${state.task.task.id}/review`,{action:decision,sql:$('#sql-editor').value,reviewer,note,revision:state.task.task.revision});
      localStorage.setItem('expertloop-reviewer',reviewer);
      const current=state.task.task.id;
      toast(`Review recorded: ${decision}. The original reference is unchanged.`);
      if(location.hash!==`#review:${current}`) location.hash=`review:${current}`; else await route();
    } else if(action==='pause-run') {
      await api(`/runs/${state.run.id}/pause`,{});toast('Pause requested. In-flight calls may still complete.');schedulePoll();
    } else if(action==='resume-run') {
      let extra=0;
      if(state.run.request_count>=state.run.max_requests) {
        const answer=window.prompt('Request cap reached. Additional request allowance (1–1000). Live requests may incur charges.','100');
        if(answer===null)return;
        extra=Number(answer);
        if(!Number.isInteger(extra)||extra<1||extra>1000)throw new Error('Enter an integer allowance from 1 to 1000.');
      }
      state.run=await api(`/runs/${state.run.id}/resume`,{extra_requests:extra});
      $('#content').innerHTML=renderExperiments(state.dashboard,state.run);schedulePoll();
    }
  } finally {element.disabled=false;}
}

document.addEventListener('click', async event=>{
  const action=event.target.closest('[data-action]');
  try {
    if(action) {event.preventDefault();await handleAction(action.dataset.action,action);return;}
    const row=event.target.closest('[data-task-link]');
    if(row) {location.hash=`review:${row.dataset.taskLink}`;return;}
    const result=event.target.closest('[data-result-link]');
    if(result) {
      state.expandedResult=result.dataset.resultLink;
      $('#content').innerHTML=renderExperiments(state.dashboard,state.run);
      $('#result-detail')?.scrollIntoView({behavior:'smooth',block:'start'});
    }
  } catch(error){toast(error.message,true);}
});
document.addEventListener('keydown',event=>{
  if((event.key==='Enter'||event.key===' ') && event.target.matches('[data-task-link],[data-result-link]')) {event.preventDefault();event.target.click();}
});
document.addEventListener('change',event=>{
  if(event.target.id==='category-filter'){state.category=event.target.value;$('#content').innerHTML=renderDataset();}
  if(event.target.id==='status-filter'){state.status=event.target.value;$('#content').innerHTML=renderDataset();}
  if(event.target.id==='run-select'){state.expandedResult=null;location.hash=`experiments:${event.target.value}`;}
  if(event.target.id==='provider-select')providerNote();
});
document.addEventListener('input',event=>{
  if(event.target.id==='task-search'){
    const cursor=event.target.selectionStart;state.search=event.target.value;
    $('#content').innerHTML=renderDataset();$('#task-search').focus();$('#task-search').setSelectionRange(cursor,cursor);
  }
});
$('#run-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const button=$('#start-run');button.disabled=true;
  try {
    const form=new FormData(event.target);
    const payload=Object.fromEntries(form.entries());
    for(const field of ['concurrency','few_shot_limit','max_requests','max_output_tokens'])payload[field]=Number(payload[field]);
    state.run=await api('/runs',payload);
    $('#run-dialog').close();state.expandedResult=null;
    location.hash=`experiments:${state.run.id}`;
  } catch(error){toast(error.message,true);} finally{button.disabled=false;}
});
window.addEventListener('hashchange',()=>{state.expandedResult=null;route();});
route();
