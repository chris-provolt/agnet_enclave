/* Timeline player: replays a run's events with real inter-event timing (scaled),
   or live-tails a running run over SSE. */
(function () {
  const body = document.body;
  const runId = body.dataset.runId;
  const runStatus = body.dataset.runStatus;
  const el = {
    timeline: document.getElementById('timeline'),
    play: document.getElementById('btn-play'),
    step: document.getElementById('btn-step'),
    end: document.getElementById('btn-end'),
    reset: document.getElementById('btn-reset'),
    speed: document.getElementById('speed'),
    clock: document.getElementById('clock'),
    progress: document.getElementById('progress'),
    live: document.getElementById('live'),
    scrub: document.getElementById('scrub'),
    agentFilters: document.getElementById('agent-filters'),
    kindFilters: document.getElementById('kind-filters'),
  };

  const KIND_GROUPS = {
    'run.started': 'run', 'run.finished': 'run', 'run.halted': 'run', 'run.failed': 'run', 'run.stage': 'run',
    'task.assigned': 'task', 'task.result': 'task',
    'msg': 'msg', 'thought': 'thought', 'text': 'text',
    'tool.call': 'tool', 'tool.result': 'tool',
    'llm.usage': 'usage', 'llm.refusal': 'error', 'error': 'error',
    'artifact': 'artifact', 'approval.decision': 'approval', 'control': 'control', 'agent.status': 'status',
  };
  const DEFAULT_HIDDEN = new Set(['usage', 'status']);

  let events = [];
  let shown = 0;          // number of events revealed (index into events)
  let rendered = 0;       // number of events appended to DOM since last full render
  let playing = false;
  let timer = null;
  let live = false;
  const hiddenAgents = new Set();
  const hiddenKinds = new Set(DEFAULT_HIDDEN);

  function group(kind) { return KIND_GROUPS[kind] || 'other'; }
  function fmtTs(ts) { const d = new Date(ts); return d.toISOString().replace('T', ' ').replace('Z', ''); }
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function pre(obj) { return '<pre>' + esc(typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)) + '</pre>'; }

  function visible(ev) { return !hiddenAgents.has(ev.sender) && !hiddenKinds.has(group(ev.kind)); }

  function bodyFor(ev) {
    const p = ev.payload || {};
    switch (ev.kind) {
      case 'thought': return (p.source === 'note' ? '[note] ' : '') + esc(p.text || '');
      case 'text': return esc((p.text || '').slice(0, 1500)) + ((p.text || '').length > 1500 ? ' ...' : '');
      case 'msg': return esc(p.text || '');
      case 'tool.call': return `<details><summary>${esc(p.side)} ${esc(p.tool)}(...)</summary>${pre(p.input)}</details>`;
      case 'tool.result': {
        const summary = p.tool === 'web_search' ? `${p.count || 0} results` : (p.is_error ? 'error' : 'ok');
        const detail = p.results ? p.results.map(r => `- ${esc(r.title || '')} ${esc(r.url || '')}`).join('\n') : (p.output !== undefined ? p.output : p);
        return `<details><summary>${esc(p.side)} ${esc(p.tool)} -> ${esc(summary)}</summary>${pre(detail)}</details>`;
      }
      case 'llm.usage': { const u = ev.usage || {}; return `turn ${p.turn} ${esc(p.stop_reason || '')} | in ${u.input_tokens} out ${u.output_tokens} cache_read ${u.cache_read_input_tokens} | $${Number(u.cost_usd || 0).toFixed(4)}`; }
      case 'task.assigned': return `assigned ${esc(p.task_type)} <span class="muted">${esc(p.task_id)}</span>` + (p.brief ? ` brief <strong>${esc(p.brief.name)}</strong>` : '') + (p.opportunity ? ` for <strong>${esc(p.opportunity.title || p.opportunity.id)}</strong>` + (p.round !== undefined ? ` (round ${p.round})` : '') : '');
      case 'task.result': return `${esc(p.task_type)} <span class="muted">${esc(p.task_id)}</span>: <strong>${esc(p.status)}</strong> in ${p.elapsed_s}s` + (p.error ? ` - ${esc(p.error)}` : '') + (p.result ? `<details><summary>result</summary>${pre(p.result)}</details>` : '');
      case 'artifact': return `${esc(p.artifact_type)} <strong>${esc(p.name)}</strong><details><summary>content</summary>${pre(p.content)}</details>`;
      case 'run.started': return `run started (mode ${esc((p.settings || {}).mode)}, model ${esc((p.settings || {}).model)}, cap $${(p.settings || {}).max_run_usd})` + (p.note ? ` note: ${esc(p.note)}` : '');
      case 'run.stage': return `stage: <strong>${esc(p.stage)}</strong> (spend so far $${Number(p.cost_usd || 0).toFixed(2)})`;
      case 'run.finished': case 'run.halted': case 'run.failed': return `${esc(ev.kind)} ${esc(p.reason || '')} spend $${Number(p.cost_usd || 0).toFixed(2)}` + (p.report_title ? ` report: ${esc(p.report_title)}` : '');
      case 'approval.decision': return `operator decision: <strong>${esc(p.decision)}</strong>` + (p.notes ? ` - ${esc(p.notes)}` : '');
      case 'error': return `<strong>${esc(p.where || 'error')}</strong> ${esc(p.reason || p.kind || '')}` + (p.trace ? `<details><summary>trace</summary>${pre(p.trace)}</details>` : '');
      case 'llm.refusal': return `model refused: ${esc(p.category || '')} ${esc(p.explanation || '')}`;
      default: return pre(p);
    }
  }

  function card(ev) {
    const div = document.createElement('div');
    div.className = `ev a-${ev.sender} k-${group(ev.kind)}`;
    const to = ev.recipient ? `<span class="to"> -> ${esc(ev.recipient)}</span>` : '';
    div.innerHTML = `<div class="ts">${fmtTs(ev.ts)}<br><span class="muted">#${ev.seq}</span></div>` +
      `<div class="who">${esc(ev.sender)}${to}</div>` +
      `<div class="body"><span class="kind">${esc(ev.kind)}</span>${bodyFor(ev)}</div>`;
    return div;
  }

  function fullRender() {
    el.timeline.innerHTML = '';
    rendered = 0;
    appendUpTo(shown);
  }

  function appendUpTo(n) {
    const frag = document.createDocumentFragment();
    for (let i = rendered; i < n; i++) if (visible(events[i])) frag.appendChild(card(events[i]));
    rendered = n;
    el.timeline.appendChild(frag);
    updateHud();
  }

  function updateHud() {
    const cur = shown > 0 ? events[shown - 1] : null;
    el.clock.textContent = cur ? fmtTs(cur.ts) : '-';
    el.progress.textContent = `${shown} / ${events.length} events`;
    el.scrub.max = events.length;
    el.scrub.value = shown;
    el.play.textContent = playing ? 'Pause' : 'Play';
  }

  function reveal(n) {
    n = Math.max(0, Math.min(n, events.length));
    if (n < shown) { shown = n; fullRender(); return; }
    shown = n;
    appendUpTo(shown);
    if (playing) window.scrollTo(0, document.body.scrollHeight);
  }

  function scheduleNext() {
    clearTimeout(timer);
    if (!playing) return;
    if (shown >= events.length) { if (!live) { playing = false; updateHud(); } return; }
    const speed = Number(el.speed.value) || 20;
    let delay = 150;
    if (shown > 0) {
      const gap = new Date(events[shown].ts) - new Date(events[shown - 1].ts);
      delay = Math.max(40, Math.min(2500, gap / speed));
    }
    timer = setTimeout(() => { reveal(shown + 1); scheduleNext(); }, delay);
  }

  function buildFilters() {
    const agents = [...new Set(events.map(e => e.sender))].sort();
    const kinds = [...new Set(events.map(e => group(e.kind)))].sort();
    const mk = (container, items, hidden, cls) => {
      container.querySelectorAll('label').forEach(l => l.remove());
      items.forEach(name => {
        const label = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox'; cb.checked = !hidden.has(name);
        cb.addEventListener('change', () => { cb.checked ? hidden.delete(name) : hidden.add(name); fullRender(); });
        label.appendChild(cb); label.appendChild(document.createTextNode(' ' + name));
        if (cls) label.className = cls + name;
        container.appendChild(label);
      });
    };
    mk(el.agentFilters, agents, hiddenAgents, 'a-');
    mk(el.kindFilters, kinds, hiddenKinds, '');
  }

  function startLive() {
    live = true;
    el.live.classList.remove('hidden');
    const after = events.length ? events[events.length - 1].event_id : '$';
    const es = new EventSource(`/api/runs/${runId}/live?after=${encodeURIComponent(after)}`);
    es.addEventListener('ev', (m) => {
      const ev = JSON.parse(m.data);
      if (events.some(e => e.event_id === ev.event_id)) return;
      events.push(ev);
      if (!events.some(e => e.sender === ev.sender) || true) buildFilters();
      if (shown === events.length - 1) reveal(events.length); else updateHud();
      if (ev.kind === 'run.finished' || ev.kind === 'run.failed' || (ev.kind === 'run.halted' && ev.payload && ev.payload.status)) {
        el.live.textContent = 'ENDED'; es.close(); live = false;
      }
    });
    es.onerror = () => { el.live.textContent = 'LIVE (reconnecting)'; };
  }

  async function load() {
    const res = await fetch(`/api/runs/${runId}/events`);
    events = await res.json();
    buildFilters();
    if (runStatus === 'running') {
      shown = 0; reveal(events.length); startLive();
    } else {
      shown = 0; updateHud();
    }
  }

  el.play.addEventListener('click', () => { playing = !playing; updateHud(); if (playing) { if (shown >= events.length) shown = 0, fullRender(); scheduleNext(); } });
  el.step.addEventListener('click', () => { playing = false; reveal(shown + 1); updateHud(); });
  el.end.addEventListener('click', () => { playing = false; reveal(events.length); updateHud(); });
  el.reset.addEventListener('click', () => { playing = false; clearTimeout(timer); shown = 0; fullRender(); });
  el.scrub.addEventListener('input', () => { playing = false; clearTimeout(timer); reveal(Number(el.scrub.value)); updateHud(); });
  el.speed.addEventListener('change', () => { if (playing) scheduleNext(); });

  load();
})();
