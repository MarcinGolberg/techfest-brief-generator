// ── Chat UI — rendering helpers ───────────────────────────────────────────────

function showBriefPanel() {
  document.getElementById('brief-panel').classList.add('visible');
  document.querySelector('.chat-body').classList.add('split');
}

function renderBriefPanelHeader() {
  const header = document.querySelector('.brief-panel-header');
  if (!header) return;

  if (briefPanelMode === 'document' && currentDocumentBrief) {
    header.innerHTML = `
      <span class="brief-panel-title">Podgląd dokumentu</span>
      <div class="brief-panel-actions" id="brief-panel-actions" style="display:flex;">
        <button class="btn btn-primary btn-sm" onclick="returnToBriefView()">← Edytuj</button>
        ${currentDocumentDownloadUrl
          ? `<a class="btn btn-primary btn-sm" href="${currentDocumentDownloadUrl}" download>↓ DOCX</a>`
          : ''}
        <button class="btn btn-primary btn-sm" id="btn-pdf-download" onclick="downloadAsPdf(this)">↓ PDF</button>
        ${!currentBadgeGeneration
          ? '<button class="btn btn-primary btn-sm" id="btn-accept-brief" onclick="acceptDocumentBrief(this)">Akceptuj brief &gt;</button>'
          : '<button class="btn btn-primary btn-sm" id="btn-accept-brief" onclick="acceptDocumentBrief(this)">Generuj ponownie &gt;</button>'}
      </div>`;
    return;
  }

  header.innerHTML = `
    <span class="brief-panel-title">Podgląd briefu</span>
    <div class="brief-panel-actions" id="brief-panel-actions" style="display:${chatMode === 'editing' ? 'flex' : 'none'};">
      <button class="btn btn-primary btn-sm" onclick="finalizeBrief()">Generuj dokument &gt;</button>
    </div>`;
}

function renderBriefPanel() {
  const content = document.getElementById('brief-panel-content');
  const missingSet = new Set(currentMissing.map(f => f.field));
  const currentField = currentMissing[0]?.field;

  content.innerHTML = BRIEF_SCHEMA.map(({ field, label, type }) => {
    const value  = currentBrief?.[field];
    const isList = type === 'list';
    let displayValue = '—';
    let hasValue = false;

    if (value) {
      if (isList && Array.isArray(value) && value.length > 0) {
        displayValue = value.map(v => `<span class="brief-tag">${escapeHtml(String(v))}</span>`).join('');
        hasValue = true;
      } else if (!isList && typeof value === 'string' && value.trim()) {
        displayValue = escapeHtml(value.trim());
        hasValue = true;
      }
    }

    const isCurrent = field === currentField;
    let cls = 'brief-field-empty';
    if (isCurrent)     cls = 'brief-field-current';
    else if (hasValue) cls = 'brief-field-filled';

    return `<div class="brief-field ${cls}" data-field="${field}">
      <div class="brief-field-label">${label}</div>
      <div class="brief-field-value">${displayValue}</div>
    </div>`;
  }).join('');
}

function flashBriefField(fieldName) {
  const el = document.querySelector(`[data-field="${fieldName}"]`);
  if (!el) return;
  el.classList.remove('brief-field-updated');
  void el.offsetWidth; // force reflow so the animation restarts
  el.classList.add('brief-field-updated');
  setTimeout(() => el.classList.remove('brief-field-updated'), 1300);
}

function renderSidebar() {
  const list       = document.getElementById('brief-progress-list');
  const missingSet = new Set(currentMissing.map(f => f.field));
  const current    = currentMissing[0]?.field;

  list.innerHTML = BRIEF_SCHEMA.map(({ field, label }) => {
    const cls  = missingSet.has(field)
      ? (field === current ? 'progress-current' : 'progress-missing')
      : 'progress-done';
    const icon = cls === 'progress-done' ? '✓' : (cls === 'progress-current' ? '◉' : '○');
    return `<div class="progress-item ${cls}">
      <span class="progress-icon">${icon}</span><span>${label}</span>
    </div>`;
  }).join('');

  renderBriefPanel();
}

function updateInputPlaceholder(isList) {
  document.getElementById('chat-input').placeholder = isList
    ? 'Np. Instagram, LinkedIn, e-mail…'
    : 'Wpisz odpowiedź…';
}

function addAIMessage(html, focusInput) {
  if (html == null) return;
  const msgs = document.getElementById('chat-messages');

  // Show typing indicator first
  const typing = document.createElement('div');
  typing.className = 'typing-wrap';
  typing.innerHTML = `
    <div class="chat-avatar">A</div>
    <div class="typing-bubble">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;
  msgs.appendChild(typing);
  msgs.scrollTop = msgs.scrollHeight;

  setTimeout(() => {
    typing.remove();
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg-ai';
    div.innerHTML = `<div class="chat-avatar">A</div><div class="chat-bubble">${html}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    if (focusInput) document.getElementById('chat-input').focus();
  }, 600);
}

function addUserMessage(text) {
  const msgs = document.getElementById('chat-messages');
  const div  = document.createElement('div');
  div.className = 'chat-msg chat-msg-user';
  div.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}
