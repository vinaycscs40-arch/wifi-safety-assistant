/**
 * Wi-Fi Safety Assistant – Frontend Application JS
 * IBM Inter-Institute Hackathon
 */

const API_BASE = '';  // same-origin; Flask serves both

// ════════════════════════════════════════════════════════════
// STATE
// ════════════════════════════════════════════════════════════
let lastReport = null;
let analyticsLoaded = false;

// ════════════════════════════════════════════════════════════
// NAVIGATION
// ════════════════════════════════════════════════════════════
function switchPanel(panelId) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('panel-' + panelId);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`.nav-btn[data-panel="${panelId}"]`);
  if (btn) btn.classList.add('active');
  if (panelId === 'history') loadHistory();
  if (panelId === 'analytics') loadAnalytics();
}

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => switchPanel(btn.dataset.panel));
});

// ════════════════════════════════════════════════════════════
// BOOTSTRAP: health check + model status
// ════════════════════════════════════════════════════════════
async function checkHealth() {
  const dot = document.getElementById('backendStatus');
  const label = document.getElementById('backendStatusLabel');
  dot.className = 'status-dot checking';
  label.textContent = 'Connecting…';

  try {
    const r = await fetch(`${API_BASE}/api/health`);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    dot.className = 'status-dot ok';
    label.textContent = 'Backend Online';
    updateModelBadges(data.models);
    loadQuickStats();
  } catch (e) {
    dot.className = 'status-dot error';
    label.textContent = 'Backend Offline';
    setAllModelBadges('error', '⚠ Offline');
    console.error('Health check failed:', e);
  }
}

function updateModelBadges(models) {
  if (!models) return;
  updateOneBadge('modelGranite', models.granite, 'granite');
  updateOneBadge('modelGroq', models.groq, 'groq');
  updateOneBadge('modelGemini', models.gemini, 'gemini');
}

function updateOneBadge(cardId, info, name) {
  const card = document.getElementById(cardId);
  if (!card || !info) return;
  const badge = card.querySelector('.model-badge');
  if (info.available) {
    badge.className = 'model-badge ok';
    badge.textContent = '● Active';
  } else {
    badge.className = 'model-badge unavailable';
    badge.textContent = 'Not configured';
  }
}

function setAllModelBadges(cls, text) {
  ['modelGranite','modelGroq','modelGemini'].forEach(id => {
    const b = document.querySelector(`#${id} .model-badge`);
    if (b) { b.className = `model-badge ${cls}`; b.textContent = text; }
  });
}

// ════════════════════════════════════════════════════════════
// QUICK STATS
// ════════════════════════════════════════════════════════════
async function loadQuickStats() {
  try {
    const r = await fetch(`${API_BASE}/api/analytics`);
    const data = await r.json();
    if (!data.success) return;
    const a = data.analytics;
    setText('statTotal', a.total_tasks ?? '—');
    setText('statHigh', a.risk_distribution?.HIGH ?? '—');
    setText('statMedium', a.risk_distribution?.MEDIUM ?? '—');
    setText('statLow', a.risk_distribution?.LOW ?? '—');
  } catch (e) { /* non-critical */ }
}

// ════════════════════════════════════════════════════════════
// ASSESSMENT FORM
// ════════════════════════════════════════════════════════════
document.getElementById('assessForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('assessBtn');
  const btnText = document.getElementById('assessBtnText');

  const payload = {
    wifi_name: document.getElementById('wifiName').value.trim(),
    connection_type: document.getElementById('connectionType').value,
    location: document.getElementById('location').value.trim(),
    user_context: document.getElementById('userContext').value.trim(),
  };

  if (!payload.wifi_name) {
    alert('Please enter the Wi-Fi network name.');
    return;
  }

  btn.disabled = true;
  btnText.textContent = '⏳ Analyzing…';
  showLoadingOverlay();
  setAllAgentStatuses('idle');

  // Animate loading steps
  const steps = [
    { label: 'Guardrail validation', agentId: null },
    { label: 'Agent 1: Network Risk Assessment (IBM Granite)', agentId: 'pipeAgent1' },
    { label: 'Agent 2: Device Safety & Prevention (IBM Granite)', agentId: 'pipeAgent2' },
    { label: 'Agent 3: Incident Response (Groq/Gemini)', agentId: 'pipeAgent3' },
    { label: 'Supervisor consolidation', agentId: 'pipeSupervisor' },
  ];
  renderLoadingSteps(steps);
  animateLoadingSteps(steps, 2800);

  try {
    const r = await fetch(`${API_BASE}/api/assess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    hideLoadingOverlay();
    btn.disabled = false;
    btnText.textContent = '🔍 Analyze with AI Agents';

    if (data.success) {
      lastReport = data;
      renderResults(data);
      document.getElementById('assessResults').classList.remove('hidden');
      document.getElementById('assessResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (data.blocked) {
      showError(data.reason || 'Request blocked by safety guardrails.');
    } else {
      showError(data.error || 'Assessment failed. Please try again.');
    }
  } catch (err) {
    hideLoadingOverlay();
    btn.disabled = false;
    btnText.textContent = '🔍 Analyze with AI Agents';
    showError('Could not reach the backend. Please ensure the server is running on port 5000.');
    console.error('Assessment error:', err);
  }
});

function clearAssessForm() {
  document.getElementById('assessForm').reset();
  document.getElementById('assessResults').classList.add('hidden');
}

// ════════════════════════════════════════════════════════════
// RENDER RESULTS
// ════════════════════════════════════════════════════════════
function renderResults(data) {
  renderRiskBadge(data);
  renderWarningSigns(data.warning_signs || []);
  renderChecklist(data.device_checklist || []);
  renderBanking(data.banking_guidance || {});
  renderAgentLog(data);
  renderFinalReport(data.final_report || {}, data);
  updateAgentStatusCards(data.agent_statuses || {});
}

function renderRiskBadge(data) {
  const risk = data.risk_level || 'UNKNOWN';
  const score = data.risk_score || 0;
  const badge = document.getElementById('riskBadgeLarge');
  badge.textContent = risk;
  badge.className = 'risk-badge-large ' + risk;
  document.getElementById('riskScoreFill').style.width = score + '%';
  document.getElementById('riskExplanation').textContent =
    data.risk_explanation || data.risk_summary || '';
}

function renderWarningSigns(signs) {
  const card = document.getElementById('warningSigns');
  const list = document.getElementById('warningSignsList');
  if (!signs.length) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  list.innerHTML = signs.map(s => `<li>${escHtml(s)}</li>`).join('');
}

function renderChecklist(items) {
  const el = document.getElementById('deviceChecklist');
  document.getElementById('checklistBadge').textContent = items.length + ' items';
  if (!items.length) { el.innerHTML = '<p class="loading-msg">No checklist items.</p>'; return; }
  el.innerHTML = items.map(item => `
    <div class="checklist-item">
      <span class="checklist-priority ${item.priority}">${item.priority}</span>
      <div>
        <div class="checklist-action">${escHtml(item.action)}</div>
        <div class="checklist-why">${escHtml(item.why)}</div>
      </div>
    </div>`).join('');
}

function renderBanking(banking) {
  const el = document.getElementById('bankingGuidance');
  const rec = banking.recommendation || '';
  const details = banking.details || [];
  const emergency = banking.emergency || '';
  const cls = rec.includes('AVOID') ? 'AVOID' : rec.includes('CAUTION') ? 'CAUTION' : 'standard';
  el.innerHTML = `
    <div class="banking-rec ${cls}">${escHtml(rec)}</div>
    ${details.map(d => `<div class="banking-detail">${escHtml(d)}</div>`).join('')}
    ${emergency ? `<div class="banking-emergency">⚠️ ${escHtml(emergency)}</div>` : ''}`;
}

function renderAgentLog(data) {
  const el = document.getElementById('agentExecutionLog');
  const log = data.execution_log || [];
  const agents = data.agent_statuses || {};

  const steps = log.map(entry => {
    const icon = entry.status === 'complete' || entry.status === 'passed' ? '✅' :
                 entry.status === 'running' ? '⏳' :
                 entry.status === 'error' || entry.status === 'blocked' ? '❌' : '•';
    return `
      <div class="exec-step">
        <span class="exec-icon">${icon}</span>
        <div>
          <div class="exec-step-name">${escHtml(entry.step)}</div>
          <div class="exec-step-detail">${entry.timestamp ? entry.timestamp.split('T')[1].slice(0,8) : ''} ${escHtml(entry.details || '')}</div>
        </div>
        <span class="exec-status-badge ${entry.status}">${entry.status}</span>
      </div>`;
  });

  // Add provider info
  Object.values(agents).forEach(a => {
    if (a.model) {
      steps.push(`
        <div class="exec-step">
          <span class="exec-icon">🤖</span>
          <div>
            <div class="exec-step-name">${escHtml(a.name)}</div>
            <div class="exec-step-detail mono">${escHtml(a.model)} · ${a.provider} · ${a.duration_ms}ms</div>
          </div>
          <span class="exec-status-badge complete">${a.status}</span>
        </div>`);
    }
  });

  el.innerHTML = steps.join('') || '<p class="loading-msg">No execution log available.</p>';
}

function renderFinalReport(report, data) {
  const el = document.getElementById('finalReport');
  if (!report || !report.report_id) {
    el.innerHTML = `<pre class="mono" style="white-space:pre-wrap;font-size:11px;color:var(--text-muted)">${escHtml(JSON.stringify(data,null,2).slice(0,2000))}</pre>`;
    return;
  }
  const steps = (report.critical_actions || []).concat(report.high_priority_actions || []).slice(0,6);
  el.innerHTML = `
    <div class="report-section">
      <div class="info-row"><span class="info-label">Report ID</span><span class="info-value mono">${escHtml(report.report_id||'')}</span></div>
      <div class="info-row"><span class="info-label">Network</span><span class="info-value">${escHtml(report.network||'')}</span></div>
      <div class="info-row"><span class="info-label">Location</span><span class="info-value">${escHtml(report.location||'')}</span></div>
      <div class="info-row"><span class="info-label">Risk Score</span><span class="info-value">${report.risk_score || 0}/100</span></div>
      <div class="info-row"><span class="info-label">Scenario</span><span class="info-value">${escHtml(report.incident_scenario||'general')}</span></div>
      <div class="info-row"><span class="info-label">Models Used</span><span class="info-value mono">${(report.models_used||[]).join(', ')}</span></div>
    </div>
    ${steps.length ? `
    <div class="report-section">
      <h4>Top Actions</h4>
      ${steps.map(s=>`<div class="report-item">${escHtml(s)}</div>`).join('')}
    </div>` : ''}
    <div class="report-section">
      <h4>Reporting Resources</h4>
      ${(report.reporting_resources||[]).map(r=>`
        <div class="report-item">${escHtml(r.name)}${r.helpline ? ' – Helpline: '+r.helpline : ''}</div>`).join('')}
    </div>`;
}

function updateAgentStatusCards(statuses) {
  const map = {agent1:'pipeAgent1', agent2:'pipeAgent2', agent3:'pipeAgent3'};
  Object.entries(map).forEach(([key, id]) => {
    const info = statuses[key];
    if (!info) return;
    const el = document.getElementById(id);
    if (!el) return;
    const statusEl = el.querySelector('.agent-status');
    if (statusEl) {
      statusEl.className = 'agent-status complete';
      statusEl.textContent = 'Complete';
    }
    el.classList.remove('running');
    el.classList.add('complete');
  });
  const sup = document.getElementById('pipeSupervisor');
  if (sup) {
    const s = sup.querySelector('.agent-status');
    if (s) { s.className = 'agent-status complete'; s.textContent = 'Done'; }
    sup.classList.add('complete');
  }
}

// ════════════════════════════════════════════════════════════
// LOADING OVERLAY
// ════════════════════════════════════════════════════════════
function showLoadingOverlay() {
  document.getElementById('loadingOverlay').classList.remove('hidden');
  document.getElementById('loadingTitle').textContent = 'AI Agents Analyzing…';
}

function hideLoadingOverlay() {
  document.getElementById('loadingOverlay').classList.add('hidden');
}

function renderLoadingSteps(steps) {
  const el = document.getElementById('loadingSteps');
  el.innerHTML = steps.map((s, i) =>
    `<div class="loading-step" id="lstep-${i}">⏸ ${s.label}</div>`
  ).join('');
}

function animateLoadingSteps(steps, totalMs) {
  const delay = totalMs / steps.length;
  steps.forEach((s, i) => {
    setTimeout(() => {
      const el = document.getElementById('lstep-' + i);
      if (el) {
        el.className = 'loading-step active';
        el.textContent = '⏳ ' + s.label;
        if (s.agentId) setAgentStatus(s.agentId, 'running');
      }
      // prev step done
      if (i > 0) {
        const prev = document.getElementById('lstep-' + (i-1));
        if (prev) {
          prev.className = 'loading-step done';
          prev.textContent = '✅ ' + steps[i-1].label;
          if (steps[i-1].agentId) setAgentStatus(steps[i-1].agentId, 'complete');
        }
      }
    }, delay * i);
  });
}

function setAgentStatus(id, status) {
  const el = document.getElementById(id);
  if (!el) return;
  const s = el.querySelector('.agent-status');
  if (s) {
    s.className = 'agent-status ' + status;
    s.textContent = status.charAt(0).toUpperCase() + status.slice(1);
  }
  el.classList.remove('idle','running','complete','error');
  el.classList.add(status);
}

function setAllAgentStatuses(status) {
  ['pipeAgent1','pipeAgent2','pipeAgent3','pipeSupervisor'].forEach(id => setAgentStatus(id, status));
}

// ════════════════════════════════════════════════════════════
// CHAT ASSISTANT
// ════════════════════════════════════════════════════════════
async function sendChat() {
  const input = document.getElementById('chatInput');
  const message = input.value.trim();
  if (!message) return;

  appendChatMsg('user', message);
  input.value = '';
  document.getElementById('chatSendBtn').disabled = true;

  const typingId = appendChatMsg('assistant', '⏳ Thinking…');

  try {
    const r = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message}),
    });
    const data = await r.json();
    updateChatMsg(typingId, data.success ? data.response : `⚠️ ${data.error || 'Error getting response'}`);
    if (data.model) {
      const meta = document.getElementById('meta-' + typingId);
      if (meta) meta.textContent = `AI Assistant · ${data.model}`;
    }
  } catch (e) {
    updateChatMsg(typingId, '⚠️ Could not reach assistant. Please check if the server is running.');
  }
  document.getElementById('chatSendBtn').disabled = false;
}

function askQuestion(q) {
  document.getElementById('chatInput').value = q;
  sendChat();
}

let _msgCounter = 0;
function appendChatMsg(role, text) {
  const id = 'msg-' + (++_msgCounter);
  const msgs = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role;
  div.id = id;
  div.innerHTML = `
    <div class="chat-bubble">${escHtml(text).replace(/\n/g,'<br/>')}</div>
    <div class="chat-meta" id="meta-${id}">${role === 'user' ? 'You' : 'AI Assistant'}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function updateChatMsg(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  const bubble = el.querySelector('.chat-bubble');
  if (bubble) bubble.innerHTML = escHtml(text).replace(/\n/g,'<br/>');
}

// ════════════════════════════════════════════════════════════
// HISTORY
// ════════════════════════════════════════════════════════════
async function loadHistory() {
  const el = document.getElementById('historyTable');
  el.innerHTML = '<div class="loading-msg">Loading…</div>';
  try {
    const r = await fetch(`${API_BASE}/api/tasks?limit=30`);
    const data = await r.json();
    if (!data.success || !data.tasks.length) {
      el.innerHTML = '<div class="loading-msg">No assessments yet. Run your first risk assessment!</div>';
      return;
    }
    const rows = data.tasks.map(t => `
      <tr>
        <td class="mono">${t.id.slice(0,8)}…</td>
        <td>${escHtml(t.wifi_name || '—')}</td>
        <td><span class="risk-pill ${t.risk_level||'UNKNOWN'}">${t.risk_level||'—'}</span></td>
        <td><span class="exec-status-badge ${t.status}">${t.status}</span></td>
        <td>${t.total_duration_ms ? Math.round(t.total_duration_ms)+'ms' : '—'}</td>
        <td class="mono" style="color:var(--text-muted)">${(t.created_at||'').replace('T',' ').slice(0,19)}</td>
      </tr>`).join('');
    el.innerHTML = `
      <table class="history-table">
        <thead><tr><th>ID</th><th>Network</th><th>Risk</th><th>Status</th><th>Duration</th><th>Time</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    el.innerHTML = '<div class="error-msg">Failed to load history. Backend may be offline.</div>';
  }
}

// ════════════════════════════════════════════════════════════
// ANALYTICS
// ════════════════════════════════════════════════════════════
async function loadAnalytics() {
  try {
    const r = await fetch(`${API_BASE}/api/analytics`);
    const data = await r.json();
    if (!data.success) return;
    const a = data.analytics;

    setText('anaTotal', a.total_tasks ?? '—');
    setText('anaComplete', a.complete ?? '—');
    setText('anaErrors', a.errors ?? '—');

    renderProviderStats(a.provider_stats || {});
    renderRiskDist(a.risk_distribution || {}, a.total_tasks || 0);
    renderAgentHandoffs(a);
  } catch (e) {
    document.getElementById('providerStats').innerHTML = '<div class="error-msg">Could not load analytics.</div>';
  }
}

function renderProviderStats(stats) {
  const el = document.getElementById('providerStats');
  if (!Object.keys(stats).length) {
    el.innerHTML = '<div class="loading-msg">No API calls recorded yet. Run an assessment first.</div>';
    return;
  }
  const names = {granite:'IBM Granite (watsonx.ai)', gemini:'Google Gemini', groq:'Groq'};
  el.innerHTML = Object.entries(stats).map(([provider, s]) => `
    <div class="provider-stat">
      <div class="provider-name">${names[provider]||provider}</div>
      <div class="provider-bar-wrap">
        <div class="provider-bar" style="width:${s.success_rate||0}%"></div>
      </div>
      <div class="provider-meta">${s.success_rate||0}% success · avg ${s.avg_ms||0}ms · ${s.total||0} calls</div>
    </div>`).join('');
}

function renderRiskDist(dist, total) {
  const el = document.getElementById('riskDistribution');
  if (!total) {
    el.innerHTML = '<div class="loading-msg">No data yet.</div>';
    return;
  }
  el.innerHTML = ['HIGH','MEDIUM','LOW'].map(level => {
    const count = dist[level] || 0;
    const pct = total ? Math.round(count/total*100) : 0;
    return `
      <div class="dist-row">
        <span class="dist-label risk-pill ${level}">${level}</span>
        <div class="dist-bar-wrap">
          <div class="dist-bar ${level}" style="width:${pct}%">${pct > 10 ? pct+'%' : ''}</div>
        </div>
        <span style="min-width:40px;text-align:right;font-size:13px">${count}</span>
      </div>`;
  }).join('');
}

function renderAgentHandoffs(a) {
  const el = document.getElementById('agentHandoffs');
  const complete = a.complete || 0;
  const total = a.total_tasks || 0;
  const rate = total ? Math.round(complete/total*100) : 0;
  el.innerHTML = `
    <div class="provider-stat">
      <div class="provider-name">Pipeline Success</div>
      <div class="provider-bar-wrap"><div class="provider-bar" style="width:${rate}%"></div></div>
      <div class="provider-meta">${rate}% (${complete}/${total})</div>
    </div>
    <div style="color:var(--text-muted);font-size:12px;margin-top:12px;padding:8px 0">
      Agent handoff: Agent 1 → Agent 2 → Agent 3 → Supervisor
    </div>`;
}

// ════════════════════════════════════════════════════════════
// DOWNLOAD REPORT
// ════════════════════════════════════════════════════════════
function downloadReport() {
  if (!lastReport) return;
  const text = JSON.stringify(lastReport, null, 2);
  const blob = new Blob([text], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `wifi-safety-report-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════
function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function showError(msg) {
  document.getElementById('assessResults').classList.remove('hidden');
  const existing = document.querySelector('.error-banner');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.className = 'card error-msg error-banner';
  div.textContent = '⚠️ ' + msg;
  document.getElementById('assessResults').prepend(div);
}

// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════
checkHealth();

// B7: Refresh model status badges every 5 minutes so they don't go stale
async function refreshModelStatus() {
  try {
    const r = await fetch(`${API_BASE}/api/models/status`);
    if (!r.ok) return;
    const data = await r.json();
    if (data.success && data.providers) updateModelBadges(data.providers);
  } catch (_) { /* non-critical */ }
}
setInterval(refreshModelStatus, 5 * 60 * 1000);
