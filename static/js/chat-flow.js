// ── Chat flow — filling, editing, manual input ────────────────────────────────

function resetGeneratedArtifacts() {
  currentDocumentBrief       = null;
  currentDocumentDownloadUrl = '';
  currentBadgeGeneration     = null;
  currentBadgeDownloadUrl    = '';
  briefPanelMode             = 'brief';
}

function startChatMode(data) {
  resetGeneratedArtifacts();
  currentBrief        = data.brief;
  currentMissing      = data.missing_fields || [];
  currentSources      = data.sources || [];
  currentCombinedText = data.combined_text || '';
  chatMode            = 'filling';

  const overlay = document.getElementById('chat-overlay');
  const label   = document.getElementById('chat-product-label');
  label.textContent = currentBrief.product_or_service || 'Brief';

  overlay.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('chat-input-bar').style.display = 'flex';
  renderSidebar();
  showBriefPanel();
  renderBriefPanelHeader();
  renderBriefPanel();

  addAIMessage(
    'Cześć! Przeanalizowałam przesłane materiały i przygotowałam wstępny brief. ' +
    'Potrzebuję jeszcze kilku uzupełnień — zadam Ci kilka krótkich pytań.'
  );

  setTimeout(() => {
    if (currentMissing.length > 0) {
      askNext();
    } else {
      addAIMessage('Wszystkie pola są już wypełnione. Brief jest kompletny!');
      showComplete();
    }
  }, 700);
}

function askNext(prefixMsg) {
  if (currentMissing.length === 0) {
    addAIMessage('Dziękuję za wszystkie odpowiedzi!');
    showComplete();
    return;
  }

  fieldConversation = [];
  invalidStreak     = 0;

  const field  = currentMissing[0];
  const isList = BRIEF_SCHEMA.find(s => s.field === field.field)?.type === 'list';
  const hint   = isList
    ? ' <span style="font-size:0.78rem;color:#555">(możesz podać kilka, oddzielonych przecinkami)</span>'
    : '';
  const questionText = (prefixMsg ? prefixMsg + ' ' : '') + field.question + hint;

  fieldConversation.push({ role: 'assistant', content: field.question });
  addAIMessage(questionText, true);
  updateInputPlaceholder(isList);
}

async function sendChatAnswer() {
  if (chatMode === 'editing') {
    await sendEditPrompt();
    return;
  }

  const input  = document.getElementById('chat-input');
  const answer = input.value.trim();
  if (!answer || currentMissing.length === 0) return;

  const field = currentMissing[0];
  input.value = '';
  input.style.height = '';
  document.getElementById('btn-chat-send').disabled = true;

  addUserMessage(answer);
  fieldConversation.push({ role: 'user', content: answer });

  try {
    const res = await fetch('/chat_answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: currentBrief,
        sources: currentSources,
        combined_text: currentCombinedText,
        field: field.field,
        conversation_history: fieldConversation,
      }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      fieldConversation.pop(); // roll back the user turn so retry works cleanly
      const detail = data.error ? ` (${data.error})` : '';
      addAIMessage(`Ups, coś poszło nie tak po mojej stronie${detail}. Spróbuj jeszcze raz!`, true);
      return;
    }

    const status = data.status;

    if (status === 'accepted') {
      const payload    = data.payload || {};
      const justFilled = field.field;
      resetGeneratedArtifacts();
      currentBrief   = payload.brief   ?? currentBrief;
      currentMissing = payload.missing_fields ?? [];
      if (payload.sources)       currentSources      = payload.sources;
      if (payload.combined_text) currentCombinedText = payload.combined_text;
      renderSidebar();
      setTimeout(() => flashBriefField(justFilled), 150);

      setTimeout(() => {
        if (currentMissing.length > 0) {
          addAIMessage(data.response, false);
          setTimeout(() => askNext(), 900);
        } else {
          addAIMessage(data.response);
          setTimeout(showComplete, 800);
        }
      }, 200);

    } else {
      // needs_more or invalid — stay on the current field
      fieldConversation.push({ role: 'assistant', content: data.response });

      if (status === 'invalid') invalidStreak++;
      else invalidStreak = 0;

      setTimeout(() => {
        addAIMessage(data.response, invalidStreak < 2);
        if (invalidStreak >= 2) {
          setTimeout(() => showManualInput(currentMissing[0]), 400);
        }
      }, 200);
    }

  } catch (err) {
    addAIMessage('Wystąpił błąd połączenia. Spróbuj ponownie.');
  } finally {
    document.getElementById('btn-chat-send').disabled = false;
  }
}

function showManualInput(fieldMeta) {
  const chatInput = document.getElementById('chat-input');
  const sendBtn   = document.getElementById('btn-chat-send');
  chatInput.disabled    = true;
  chatInput.placeholder = 'Wypełnij formularz powyżej…';
  sendBtn.disabled      = true;

  const isList = BRIEF_SCHEMA.find(s => s.field === fieldMeta.field)?.type === 'list';
  const msgs   = document.getElementById('chat-messages');
  const card   = document.createElement('div');
  card.className         = 'manual-card';
  card.dataset.field     = fieldMeta.field;
  card.dataset.fieldType = isList ? 'list' : 'string';

  card.innerHTML = `
    <div class="manual-card-header">
      <div class="manual-card-icon">✎</div>
      <div>
        <div class="manual-card-title">Wprowadź ręcznie</div>
        <div class="manual-card-subtitle">${fieldMeta.label}</div>
      </div>
    </div>
    ${isList
      ? `<p class="manual-card-hint">Wpisz wartości oddzielone przecinkami.</p>
         <textarea class="manual-field" rows="3" placeholder="Np. Instagram, LinkedIn, e-mail…"></textarea>`
      : `<input class="manual-field" type="text" placeholder="Wpisz odpowiedź…">`
    }
    <div class="manual-actions">
      <button class="btn btn-primary" onclick="submitManualInput(this)" style="padding:9px 18px;">
        Zapisz &gt;
      </button>
      <button class="btn btn-subtle" onclick="retryWithAI(this)" style="padding:9px 18px; font-size:0.75rem;">
        Wróć do rozmowy
      </button>
    </div>`;

  msgs.appendChild(card);
  msgs.scrollTop = msgs.scrollHeight;
  card.querySelector('.manual-field').focus();
}

async function submitManualInput(btn) {
  const card      = btn.closest('.manual-card');
  const fieldName = card.dataset.field;
  const input     = card.querySelector('.manual-field');
  const value     = input.value.trim();

  if (!value) {
    input.style.borderColor = '#ef4444';
    input.focus();
    setTimeout(() => input.style.borderColor = '', 1200);
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Zapisuję…';

  const prevBrief   = currentBrief;
  const prevMissing = currentMissing;

  try {
    const res  = await fetch('/update_brief', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brief: currentBrief, field: fieldName, answer: value }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    const justFilled = fieldName;
    resetGeneratedArtifacts();
    currentBrief   = data.brief;
    currentMissing = data.missing_fields;
    renderSidebar();
    setTimeout(() => flashBriefField(justFilled), 150);

    // Replace the card with a user bubble
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-msg chat-msg-user';
    userBubble.innerHTML = `<div class="chat-bubble">${escapeHtml(value)}</div>`;
    card.replaceWith(userBubble);

    // Re-enable bottom input
    const chatInput = document.getElementById('chat-input');
    const sendBtn   = document.getElementById('btn-chat-send');
    chatInput.disabled    = false;
    chatInput.placeholder = 'Wpisz odpowiedź…';
    sendBtn.disabled      = false;

    invalidStreak = 0;

    setTimeout(() => {
      if (currentMissing.length > 0) {
        addAIMessage('Zapisałam! Przechodzimy dalej.', false);
        setTimeout(() => askNext(), 800);
      } else {
        addAIMessage('Zapisałam! Brief jest teraz kompletny.');
        setTimeout(showComplete, 800);
      }
    }, 200);

  } catch (err) {
    currentBrief   = prevBrief;
    currentMissing = prevMissing;

    btn.disabled    = false;
    btn.textContent = 'Zapisz >';
    input.focus();
    addAIMessage(`Coś poszło nie tak z zapisem (${err.message}). Spróbuj ponownie.`);
  }
}

function retryWithAI(btn) {
  btn.closest('.manual-card').remove();

  const chatInput = document.getElementById('chat-input');
  const sendBtn   = document.getElementById('btn-chat-send');
  chatInput.disabled    = false;
  chatInput.placeholder = 'Wpisz odpowiedź…';
  sendBtn.disabled      = false;

  // Keep at threshold so the next invalid immediately re-shows the card
  invalidStreak = 2;
  chatInput.focus();
}

function showComplete() {
  chatMode = 'editing';

  const inputBar  = document.getElementById('chat-input-bar');
  const chatInput = document.getElementById('chat-input');
  inputBar.classList.add('edit-mode');
  chatInput.placeholder = 'Edytuj brief — np. "Zmień cel kampanii na budowanie świadomości marki"';
  chatInput.disabled    = false;
  document.getElementById('btn-chat-send').disabled = false;
  inputBar.style.display = 'flex';

  if (!document.getElementById('edit-mode-badge')) {
    const badge = document.createElement('div');
    badge.id        = 'edit-mode-badge';
    badge.className = 'edit-mode-badge';
    badge.textContent = 'Tryb edycji — wpisz polecenie, aby zmienić dowolne pole briefu';
    inputBar.parentNode.insertBefore(badge, inputBar);
  }

  renderBriefPanelHeader();

  addAIMessage(
    'Brief jest kompletny! Możesz teraz edytować dowolne pole przez czat — ' +
    'napisz np. <em>"Zmień grupę docelową na kobiety 25–40 lat"</em>. ' +
    'Gdy wszystko gotowe, wygeneruj dokument przyciskiem w panelu po prawej.'
  );
}

async function sendEditPrompt() {
  const input  = document.getElementById('chat-input');
  const prompt = input.value.trim();
  if (!prompt) return;

  input.value = '';
  input.style.height = '';
  document.getElementById('btn-chat-send').disabled = true;

  addUserMessage(prompt);

  try {
    const res  = await fetch('/edit_brief', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brief: currentBrief, prompt }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      addAIMessage(`Ups, coś poszło nie tak (${data.error || 'błąd serwera'}). Spróbuj ponownie.`, true);
      return;
    }

    resetGeneratedArtifacts();
    currentBrief   = data.brief;
    currentMissing = data.missing_fields || [];
    renderSidebar();
    renderBriefPanelHeader();

    (data.updated_fields || []).forEach(f => setTimeout(() => flashBriefField(f), 150));
    addAIMessage(data.response || 'Zaktualizowałam brief.', true);

    // If new missing fields appeared, switch back to filling mode
    if (currentMissing.length > 0) {
      chatMode = 'filling';
      const inputBar = document.getElementById('chat-input-bar');
      inputBar.classList.remove('edit-mode');
      document.getElementById('chat-input').placeholder = 'Wpisz odpowiedź…';
      const badge = document.getElementById('edit-mode-badge');
      if (badge) badge.remove();
      renderBriefPanelHeader();
      setTimeout(() => askNext(), 900);
    }

  } catch (err) {
    addAIMessage('Wystąpił błąd połączenia. Spróbuj ponownie.');
  } finally {
    document.getElementById('btn-chat-send').disabled = false;
    document.getElementById('chat-input').focus();
  }
}

function closeChatOverlay() {
  document.getElementById('chat-overlay').style.display = 'none';

  // Reset split layout
  document.getElementById('brief-panel').classList.remove('visible');
  document.querySelector('.chat-body').classList.remove('split');

  // Reset input bar
  const inputBar  = document.getElementById('chat-input-bar');
  inputBar.style.display = 'flex';
  inputBar.classList.remove('edit-mode');
  document.getElementById('chat-input').placeholder = 'Wpisz odpowiedź…';

  // Remove edit-mode badge
  const badge = document.getElementById('edit-mode-badge');
  if (badge) badge.remove();

  chatMode = 'filling';
  resetGeneratedArtifacts();
  renderBriefPanelHeader();

  const panelStatus = document.getElementById('brief-panel-status');
  if (panelStatus) panelStatus.style.display = 'none';

  document.body.style.overflow = '';
}
