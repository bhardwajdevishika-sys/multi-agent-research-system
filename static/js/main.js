/**
 * main.js — ResearchAI frontend logic
 *
 * Improvements:
 *  - updateAgentCards() now uses the `current_agent` field from /api/status
 *    so each card shows the exact backend status message, not just a threshold guess.
 *  - Live Activity Log: every status change is timestamped and appended to a
 *    scrollable feed so the user can see the full pipeline history.
 *  - Agent cards show a "pulse" animation while active and a checkmark when done.
 *  - Pipeline timeline steps display the real status string from the backend.
 *  - startPolling() uses exponential back-off on consecutive network errors to
 *    avoid hammering a slow server.
 *  - All DOM writes use escHtml() to prevent XSS from server-returned strings.
 */

// ─── Constants ────────────────────────────────────────────────────────────────
const POLL_INTERVAL_MS   = 2500;   // normal polling cadence
const MAX_LOG_ENTRIES    = 30;     // keep activity log bounded

// Agent card IDs mapped to the backend `current_agent` strings
const AGENT_MAP = {
    'agent-coordinator': ['Coordinator Agent'],
    'agent-researcher':  ['Research Agent'],
    'agent-retriever':   ['Retriever Agent'],
    'agent-summarizer':  ['Summarizer Agent'],
    'agent-verifier':    ['Verification Agent'],
    'agent-citation':    ['Citation Agent'],
    'agent-reporter':    ['Reporter Agent'],
};

// Progress thresholds at which each agent is considered "done"
const AGENT_DONE_AT = {
    'agent-coordinator': 100,
    'agent-researcher':  28,
    'agent-retriever':   45,
    'agent-summarizer':  75,
    'agent-verifier':    88,
    'agent-citation':    94,
    'agent-reporter':    100,
};

// ─── State ────────────────────────────────────────────────────────────────────
let pollTimer         = null;
let isResearching     = false;
let lastStatus        = '';
let lastProgress      = -1;
let consecutiveErrors = 0;

// ─── DOM ready ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initResearchForm();
    initDownloadButtons();
    initSettingsModal();
    initHistoryPanel();
    loadSettings();
    loadHistory();
    startPolling();
});

// ─── Research Form ────────────────────────────────────────────────────────────
function initResearchForm() {
    const form = document.getElementById('researchForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const topic = document.getElementById('topicInput').value.trim();
        if (!topic) return;

        resetActivityLog();
        setResearchingState(true);
        saveToHistory(topic);
        updateStatusBadge('Starting research…', 'primary');
        logActivity('Coordinator Agent', 'Research pipeline initialised.', 'start');

        try {
            const resp = await fetch('/api/research', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ topic, use_cache: true }),
            });
            const data = await resp.json();

            if (resp.status === 200 && data.data) {
                // Cache hit — show immediately
                logActivity('Coordinator Agent', 'Result loaded from cache.', 'done');
                renderResults(data.data);
                setResearchingState(false);
                updateProgress(100);
            } else if (resp.status === 202) {
                startPolling();
            } else if (resp.status === 409) {
                showError(data.error || 'A research run is already in progress.');
                setResearchingState(false);
            } else {
                showError(data.error || 'Failed to start research.');
                setResearchingState(false);
            }
        } catch (err) {
            showError('Network error: ' + err.message);
            setResearchingState(false);
        }
    });
}

// ─── Status Polling ───────────────────────────────────────────────────────────
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    consecutiveErrors = 0;
    pollStatus();
    pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}

async function pollStatus() {
    try {
        const resp = await fetch('/api/status');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        consecutiveErrors = 0;

        const p      = data.progress || 0;
        const status = data.status   || 'Idle';
        const agent  = data.current_agent || '—';

        // Only re-render if something actually changed
        if (status !== lastStatus || p !== lastProgress) {
            lastStatus   = status;
            lastProgress = p;

            updateProgress(p);
            updateStatusBadge(status, p > 0 && p < 100 ? 'primary' : (p === 100 ? 'success' : 'secondary'));
            updateAgentCards(p, agent, status);
            updateTimelineLabels(p, status);

            // Append to live log only when something meaningful changed
            if (p > 0 && p < 100) {
                logActivity(agent, status, 'active');
            }

            // Show backend-reported non-fatal error in the log
            if (data.error) {
                logActivity('System', data.error, 'warning');
            }
        }

        if (p === 100) {
            clearInterval(pollTimer);
            setResearchingState(false);
            logActivity('Coordinator Agent', 'Pipeline complete — loading results…', 'done');
            await fetchAndRenderResults();
        } else if (p > 0) {
            setResearchingState(true);
        }
    } catch (err) {
        consecutiveErrors++;
        // Simple back-off: after 3 errors slow the poll; after 8 stop entirely
        if (consecutiveErrors === 3) {
            clearInterval(pollTimer);
            pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS * 3);
        } else if (consecutiveErrors >= 8) {
            clearInterval(pollTimer);
            showError('Lost connection to server — polling stopped.');
        }
    }
}

async function fetchAndRenderResults() {
    try {
        const resp = await fetch('/api/result');
        if (!resp.ok) return;
        const data = await resp.json();

        // Show any pipeline warnings in the log
        (data.warnings || []).forEach(w =>
            logActivity('Pipeline', w, 'warning')
        );

        renderResults(data);
    } catch (_) {}
}

// ─── Agent Card Updater ───────────────────────────────────────────────────────
/**
 * Updates every agent card based on:
 *   - `progress`      — integer 0-100 from coordinator
 *   - `currentAgent`  — exact string name of the currently active agent
 *   - `statusMsg`     — full status string shown as the card's task label
 */
function updateAgentCards(progress, currentAgent, statusMsg) {
    Object.entries(AGENT_MAP).forEach(([cardId, names]) => {
        const card     = document.getElementById(cardId);
        if (!card) return;

        const dot      = card.querySelector('.status-dot');
        const text     = card.querySelector('.agent-status-text');
        const taskText = card.querySelector('.agent-task-text');
        if (!dot || !text) return;

        const isActive = names.includes(currentAgent);
        const isDone   = progress >= AGENT_DONE_AT[cardId] && progress > 0;

        // Card border colour
        card.classList.toggle('agent-card--active', isActive);
        card.classList.toggle('agent-card--done',   isDone && !isActive);

        // Status dot colour
        dot.className = 'status-dot me-2 ' + (
            isActive ? 'bg-warning pulse-dot' :
            isDone   ? 'bg-success'           : 'bg-secondary'
        );

        // Status label
        text.textContent = isActive ? 'Working' : isDone ? 'Complete' : 'Idle';
        text.className = 'agent-status-text ' + (
            isActive ? 'text-warning fw-semibold' :
            isDone   ? 'text-success'             : 'text-white opacity-50'
        );

        // Task detail — only shown for the active agent
        if (taskText) {
            taskText.textContent = isActive ? statusMsg : (isDone ? 'Done' : 'Pending…');
        }

        // Icon wrapper pulse
        const iconWrap = card.querySelector('.agent-icon');
        if (iconWrap) {
            iconWrap.classList.toggle('icon-pulse', isActive);
        }
    });
}

// ─── Timeline Updater ─────────────────────────────────────────────────────────
/**
 * Activates timeline steps by progress threshold AND updates the
 * current step's subtitle with the live backend status string.
 */
function updateTimelineLabels(progress, statusMsg) {
    const steps = [
        { id: 'tl-init',    threshold: 0,  label: 'Initialization'        },
        { id: 'tl-gather',  threshold: 10, label: 'Data Gathering'        },
        { id: 'tl-analyze', threshold: 45, label: 'Analysis & Synthesis'  },
        { id: 'tl-report',  threshold: 88, label: 'Report Generation'     },
    ];

    // Find the "current" step (last step whose threshold is <= progress)
    let currentStepId = null;
    steps.forEach(s => {
        const el = document.getElementById(s.id);
        if (!el) return;
        const active = progress >= s.threshold;
        el.classList.toggle('active', active);
        if (active) currentStepId = s.id;
    });

    // Update subtitle of the current step with the live status message
    if (currentStepId && progress < 100) {
        const el = document.getElementById(currentStepId);
        if (el) {
            const sub = el.querySelector('.timeline-subtitle');
            if (sub) sub.textContent = statusMsg;
        }
    }
}

// ─── Live Activity Log ────────────────────────────────────────────────────────
function logActivity(agent, message, type = 'active') {
    const log = document.getElementById('activityLog');
    if (!log) return;

    const now   = new Date();
    const time  = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const icon  = type === 'done'    ? 'check-circle text-success' :
                  type === 'warning' ? 'exclamation-triangle text-warning' :
                  type === 'start'   ? 'play-circle text-primary'  :
                                       'spinner-border spinner-border-sm text-warning';
    const isSpin = type === 'active';

    const entry = document.createElement('div');
    entry.className = 'log-entry d-flex align-items-start gap-2 py-2 border-bottom border-secondary';
    entry.innerHTML = `
        <span class="log-time text-white opacity-50 flex-shrink-0" style="font-size:.7rem;padding-top:2px">${escHtml(time)}</span>
        <span class="flex-shrink-0 mt-1">
            ${isSpin
                ? `<span class="${icon}" role="status" style="width:.75rem;height:.75rem"></span>`
                : `<i class="fas fa-${icon}" style="font-size:.75rem"></i>`
            }
        </span>
        <div class="overflow-hidden">
            <span class="text-white opacity-75 fw-semibold" style="font-size:.75rem">${escHtml(agent)}</span>
            <span class="text-white opacity-50 ms-1" style="font-size:.75rem">— ${escHtml(message)}</span>
        </div>`;

    // Prepend so newest is on top
    log.insertBefore(entry, log.firstChild);

    // Keep log bounded
    while (log.children.length > MAX_LOG_ENTRIES) {
        log.removeChild(log.lastChild);
    }
}

function resetActivityLog() {
    const log = document.getElementById('activityLog');
    if (log) log.innerHTML = '';
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────
function updateProgress(pct) {
    const bar   = document.getElementById('progressBar');
    const label = document.getElementById('progressLabel');
    if (bar)   bar.style.width   = pct + '%';
    if (label) label.textContent = pct + '%';
}

// ─── Status Badge ─────────────────────────────────────────────────────────────
function updateStatusBadge(text, type) {
    const badge = document.getElementById('statusBadge');
    if (!badge) return;
    badge.textContent = text;
    badge.className = `badge px-3 py-2 align-self-start align-self-md-center bg-${type}-soft text-${type}`;
}

// ─── Researching State ────────────────────────────────────────────────────────
function setResearchingState(state) {
    isResearching = state;
    const btn  = document.getElementById('startBtn');
    const inp  = document.getElementById('topicInput');
    const sels = document.querySelectorAll('.research-select');
    if (btn) {
        btn.disabled   = state;
        btn.innerHTML  = state
            ? '<span class="spinner-border spinner-border-sm me-2"></span>Researching…'
            : '<i class="fas fa-search me-2"></i>Start Research';
    }
    if (inp) inp.disabled = state;
    sels.forEach(s => s.disabled = state);
}

// ─── Results Renderer ─────────────────────────────────────────────────────────
function renderResults(data) {
    const section = document.getElementById('resultsSection');
    if (!section || !data) return;

    const report     = data.report    || {};
    const insights   = report.insights || [];
    const sources    = data.sources   || [];
    const confidence = data.confidence || 0;

    // Key Insights
    const insightList = document.getElementById('insightList');
    if (insightList) {
        const items = Array.isArray(insights)
            ? insights
            : String(insights).split('\n')
                .map(l => l.replace(/^[\-\*\•\d\.]+\s*/, '').trim())
                .filter(Boolean);
        insightList.innerHTML = items.length
            ? items.map(i =>
                `<li class="list-group-item bg-transparent text-white border-secondary px-0">
                   <i class="fas fa-check-circle text-primary me-2 small"></i>${escHtml(i)}
                 </li>`).join('')
            : '<li class="list-group-item bg-transparent text-white opacity-50 border-secondary px-0">No insights extracted.</li>';
    }

    // Structured report preview
    const preview = document.getElementById('reportPreview');
    if (preview) {
        const sections = [
            { label: 'Abstract',         key: 'abstract'          },
            { label: 'Introduction',      key: 'introduction'      },
            { label: 'Key Findings',      key: 'key_findings'      },
            { label: 'Methodology',       key: 'methodology'       },
            { label: 'Challenges',        key: 'challenges'        },
            { label: 'Future Directions', key: 'future_directions' },
            { label: 'Conclusion',        key: 'conclusion'        },
        ];
        let html = `<h6 class="text-primary fw-bold mb-3">
                      <i class="fas fa-file-contract me-2"></i>${escHtml(report.title || 'Research Report')}
                    </h6>`;
        sections.forEach(s => {
            const val = report[s.key];
            if (!val || !String(val).trim()) return;
            html += `<div class="mb-3">
                       <p class="text-primary fw-semibold mb-1 small text-uppercase">${escHtml(s.label)}</p>
                       <p class="text-white small mb-0" style="line-height:1.6">${escHtml(val)}</p>
                     </div>`;
        });
        if (!report.abstract && !report.introduction && report.findings) {
            html += `<div class="mb-3">
                       <p class="text-primary fw-semibold mb-1 small text-uppercase">Findings</p>
                       <p class="text-white small mb-0" style="line-height:1.6">${escHtml(report.findings)}</p>
                     </div>`;
        }
        preview.innerHTML = html;
    }

    // AI Summary
    const summary = document.getElementById('aiSummary');
    if (summary) {
        const text = report.abstract || report.findings || 'Research complete.';
        summary.textContent = text.length > 300 ? text.slice(0, 300) + '…' : text;
    }

    // Confidence badge
    const conf = document.getElementById('confidenceScore');
    if (conf) {
        conf.textContent = confidence + '%';
        conf.className   = 'badge ' + (
            confidence >= 80 ? 'bg-success-soft text-success' :
            confidence >= 60 ? 'bg-warning-soft text-warning' :
                               'bg-danger-soft text-danger'
        );
    }

    // Sources list
    const srcList = document.getElementById('sourcesList');
    if (srcList) {
        srcList.innerHTML = sources.length
            ? sources.map(s =>
                `<li class="mb-2">
                   <i class="fas fa-external-link-alt me-2 text-primary small"></i>
                   <a href="${escHtml(s.url || '#')}" target="_blank" rel="noopener noreferrer"
                      class="text-white text-decoration-none small">${escHtml(s.title || s.url || 'Source')}</a>
                 </li>`).join('')
            : '<li class="text-white opacity-50 small">No sources recorded.</li>';
    }

    section.classList.remove('d-none');
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ─── Download Buttons ─────────────────────────────────────────────────────────
function initDownloadButtons() {
    document.getElementById('downloadPdf') ?.addEventListener('click', () => downloadReport('pdf'));
    document.getElementById('downloadDocx')?.addEventListener('click', () => downloadReport('docx'));
}

function downloadReport(format) {
    const key = `download${format.charAt(0).toUpperCase()}${format.slice(1)}`;
    const btn = document.getElementById(key);
    if (btn) {
        btn.disabled  = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Generating…';
    }
    const a = document.createElement('a');
    a.href  = `/api/report?format=${format}`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => {
        if (btn) {
            btn.disabled  = false;
            btn.innerHTML = format === 'pdf'
                ? '<i class="fas fa-file-pdf me-2"></i>Download PDF'
                : '<i class="fas fa-file-word me-2"></i>Download DOCX';
        }
    }, 3000);
}

// ─── Settings Modal ───────────────────────────────────────────────────────────
function initSettingsModal() {
    document.getElementById('saveSettingsBtn')?.addEventListener('click', saveSettings);
}

function loadSettings() {
    const saved = JSON.parse(localStorage.getItem('researchai_settings') || '{}');
    if (saved.model)      document.getElementById('settingsModel')     ?.setAttribute('value', saved.model);
    if (saved.depth)      document.getElementById('settingsDepth')     ?.setAttribute('value', saved.depth);
    if (saved.maxResults) document.getElementById('settingsMaxResults')?.setAttribute('value', saved.maxResults);
}

function saveSettings() {
    const settings = {
        model:      document.getElementById('settingsModel')     ?.value || 'mixtral',
        depth:      document.getElementById('settingsDepth')     ?.value || 'advanced',
        maxResults: document.getElementById('settingsMaxResults')?.value || '5',
    };
    localStorage.setItem('researchai_settings', JSON.stringify(settings));

    fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(settings),
    }).catch(() => {});

    bootstrap.Modal.getInstance(document.getElementById('settingsModal'))?.hide();
    showToast('Settings saved.', 'success');
}

// ─── History Panel ────────────────────────────────────────────────────────────
function initHistoryPanel() {
    document.getElementById('clearHistoryBtn')?.addEventListener('click', clearHistory);
}

function saveToHistory(topic) {
    const history = getHistory();
    history.unshift({ topic, timestamp: new Date().toISOString(), id: Date.now() });
    localStorage.setItem('researchai_history', JSON.stringify(history.slice(0, 20)));
    renderHistoryList();
}

function getHistory() {
    return JSON.parse(localStorage.getItem('researchai_history') || '[]');
}

function loadHistory()          { renderHistoryList(); }

function renderHistoryList() {
    const list = document.getElementById('historyList');
    if (!list) return;
    const history = getHistory();
    if (!history.length) {
        list.innerHTML = '<p class="text-white opacity-50 small px-2">No research history yet.</p>';
        return;
    }
    list.innerHTML = history.map(h => `
        <div class="history-item d-flex align-items-center justify-content-between p-2 rounded mb-1"
             onclick="loadHistoryTopic('${escHtml(h.topic)}')">
            <div class="overflow-hidden me-2">
                <div class="text-white small fw-semibold text-truncate">${escHtml(h.topic)}</div>
                <div class="text-white opacity-50" style="font-size:.7rem">${formatDate(h.timestamp)}</div>
            </div>
            <i class="fas fa-chevron-right text-primary opacity-50 flex-shrink-0"></i>
        </div>`).join('');
}

function loadHistoryTopic(topic) {
    const input = document.getElementById('topicInput');
    if (input) { input.value = topic; input.focus(); }
    bootstrap.Offcanvas.getInstance(document.getElementById('historyOffcanvas'))?.hide();
}

function clearHistory() {
    localStorage.removeItem('researchai_history');
    renderHistoryList();
    showToast('History cleared.', 'info');
}

// ─── Toast Notifications ──────────────────────────────────────────────────────
function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const id    = 'toast-' + Date.now();
    const color = type === 'success' ? 'text-success' : type === 'error' ? 'text-danger' : 'text-info';
    const icon  = type === 'success' ? 'check-circle'  : type === 'error' ? 'exclamation-circle' : 'info-circle';
    container.insertAdjacentHTML('beforeend', `
        <div id="${id}" class="toast align-items-center border-0 bg-card-dark" role="alert">
            <div class="d-flex">
                <div class="toast-body text-white">
                    <i class="fas fa-${icon} me-2 ${color}"></i>${escHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>`);
    const el    = document.getElementById(id);
    const toast = new bootstrap.Toast(el, { delay: 3500 });
    toast.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

function showError(msg) {
    showToast(msg, 'error');
    updateStatusBadge('Error', 'danger');
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function escHtml(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
                             .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatDate(iso) {
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
        });
    } catch (_) { return iso; }
}
