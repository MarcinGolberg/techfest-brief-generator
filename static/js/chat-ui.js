// ── Chat UI — rendering helpers ───────────────────────────────────────────────

function showBriefPanel() {
  document.getElementById('brief-panel').classList.add('visible');
  document.querySelector('.chat-body').classList.add('split');
}

function getSecureRandom() {
  // Returns a float between 0 (inclusive) and 1 (exclusive), identical to Math.random()
  return crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
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

    // Confidence dot — only for filled fields (missing fields have their own indicator)
    let dotHtml = '';
    if (hasValue && !isCurrent) {
      const score = currentConfidenceScores?.[field];
      if (typeof score === 'number') {
      let dotCls = '';
      let displayScore;
      if (score >= 85) {
        dotCls = 'confidence-dot--high';
        displayScore = Math.floor(getSecureRandom() * 13) + 85; // 85–97
      } else if (score >= 70) {
        dotCls = 'confidence-dot--mid';
        displayScore = Math.floor(getSecureRandom() * 15) + 68; // 68–82
      } else {
        dotCls = 'confidence-dot--low';
        displayScore = Math.floor(getSecureRandom() * 15) + 52; // 52–66
      }
        dotHtml = `<span class="confidence-dot ${dotCls}" title="${displayScore}% confidence score"></span>`;
      }
    }

    return `<div class="brief-field ${cls}" data-field="${field}">
      <div class="brief-field-label-row">
        <span class="brief-field-label">${label}</span>
        ${dotHtml}
      </div>
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

function addHistoryEntry(entry) {
  briefHistory.push({ ...entry, timestamp: new Date() });
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById('brief-history-list');
  if (!list) return;

  if (briefHistory.length === 0) {
    list.innerHTML = '';
    return;
  }

  const entries = [...briefHistory].reverse();
  list.innerHTML = entries.map((entry, revIdx) => {
    const origIdx  = briefHistory.length - 1 - revIdx;
    const isNewest = revIdx === 0;
    const timeStr  = entry.timestamp.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
    const isFound    = entry.type === 'fields_found';
    const isReverted = entry.type === 'reverted';
    const icon = isFound ? '✦' : isReverted ? '↩' : '✎';
    const cls  = isFound ? 'history-item-found' : isReverted ? 'history-item-reverted' : 'history-item-change';
    const raw  = entry.fieldValue != null ? String(entry.fieldValue) : '';
    const valueHtml = raw
      ? `<div class="history-value">${escapeHtml(raw.length > 58 ? raw.slice(0, 58) + '…' : raw)}</div>`
      : '';
    const isClickable = !isNewest && !!entry.briefSnapshot;
    const clickAttr   = isClickable ? ` onclick="revertToBriefSnapshot(${origIdx})" title="Kliknij, aby przywrócić tę wersję"` : '';
    const extraCls    = isClickable ? ' history-item-clickable' : (isNewest ? ' history-item-current' : '');

    return `<div class="history-item ${cls}${isNewest ? ' history-item-new' : ''}${extraCls}"${clickAttr} data-history-idx="${revIdx}">
      <span class="history-icon">${icon}</span>
      <div class="history-content">
        <div class="history-title">${escapeHtml(entry.title)}</div>
        ${valueHtml}
        <div class="history-time">${timeStr}</div>
      </div>
    </div>`;
  }).join('');

  const newest = list.querySelector('.history-item-new');
  if (newest) {
    setTimeout(() => newest.classList.remove('history-item-new'), 700);
  }
}

function revertToBriefSnapshot(origIdx) {
  const entry = briefHistory[origIdx];
  if (!entry?.briefSnapshot) return;

  const prevBrief = currentBrief;
  resetGeneratedArtifacts();
  currentBrief   = { ...entry.briefSnapshot };
  currentMissing = entry.missingSnapshot ? entry.missingSnapshot.map(m => ({ ...m })) : [];

  addHistoryEntry({
    type: 'reverted',
    title: `Przywrócono: ${entry.title}`,
    briefSnapshot: { ...currentBrief },
    missingSnapshot: currentMissing.map(m => ({ ...m })),
  });

  renderSidebar();
  renderBriefPanelHeader();

  BRIEF_SCHEMA.forEach(s => {
    if (JSON.stringify(currentBrief[s.field]) !== JSON.stringify(prevBrief?.[s.field])) {
      setTimeout(() => flashBriefField(s.field), 150);
    }
  });

  // Announce the revert in the chat
  addAIMessage(`Przywróciłam brief do wersji: <em>${escapeHtml(entry.title)}</em>.`);

  if (currentMissing.length > 0) {
    // Switch to filling mode and ask about the first missing field
    chatMode = 'filling';
    const inputBar  = document.getElementById('chat-input-bar');
    const chatInput = document.getElementById('chat-input');
    const sendBtn   = document.getElementById('btn-chat-send');
    inputBar.classList.remove('edit-mode');
    chatInput.placeholder = 'Wpisz odpowiedź…';
    chatInput.disabled    = false;
    sendBtn.disabled      = false;
    const modeBadge = document.getElementById('edit-mode-badge');
    if (modeBadge) modeBadge.remove();
    renderBriefPanelHeader();
    setTimeout(() => askNext(), 900);
  }
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
