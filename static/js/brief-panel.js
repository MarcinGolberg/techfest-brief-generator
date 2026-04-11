// ── Brief panel — document generation & badge workflow ────────────────────────

async function finalizeBrief() {
  const statusEl = document.getElementById('brief-panel-status');
  statusEl.textContent = 'Trwa generowanie dokumentu…';
  statusEl.style.color = 'var(--gray-dark)';
  statusEl.style.display = 'block';

  const genBtn = document.querySelector('#brief-panel-actions .btn-primary');
  if (genBtn) genBtn.disabled = true;

  try {
    const res = await fetch('/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: currentBrief,
        sources: currentSources,
        combined_text: currentCombinedText,
        format: 'docx',
      }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      const detail = data.error ? ` (${data.error})` : '';
      statusEl.textContent = `Błąd: Nie udało się wygenerować dokumentu${detail}.`;
      statusEl.style.color = '#c00';
      return;
    }

    statusEl.style.display = 'none';
    renderDocumentPreview(data.document_brief, data.download_url);

  } catch (err) {
    statusEl.textContent = `Błąd połączenia: ${err.message}`;
    statusEl.style.color = '#c00';
  } finally {
    if (genBtn) genBtn.disabled = false;
  }
}

function renderDocumentPreview(docBrief, docxDownloadUrl) {
  briefPanelMode = 'document';
  currentDocumentBrief = docBrief;
  currentDocumentDownloadUrl = docxDownloadUrl || '';

  const panel   = document.getElementById('brief-panel');
  const content = document.getElementById('brief-panel-content');
  renderBriefPanelHeader();

  const safe     = s => s ? escapeHtml(String(s)) : '';
  const safeList = v => Array.isArray(v) ? v : [];
  const listHtml = items => items.length
    ? items.map(i => `<li class="doc-list-item">${safe(i)}</li>`).join('')
    : '<li class="doc-list-item" style="color:#555">—</li>';

  const sections = [
    { title: 'EXECUTIVE SUMMARY / STRESZCZENIE',      value: docBrief.executive_summary,  type: 'text' },
    { title: 'BACKGROUND / KONTEKST',                  value: docBrief.background,         type: 'text' },
    { title: 'OBJECTIVE / CEL',                        value: docBrief.objective,          type: 'text' },
    { title: 'TARGET GROUP / GRUPA DOCELOWA',          value: docBrief.target_group,       type: 'text' },
    { title: 'ISSUE / PROBLEM',                        value: docBrief.issue,              type: 'text' },
    { title: 'INSIGHT / OBSERWACJA',                   value: docBrief.insight,            type: 'text' },
    { title: 'CREATIVE CHALLENGE / WYZWANIE KREATYWNE', value: docBrief.creative_challenge, type: 'text' },
    { title: 'MANDATORIES / WYMAGANIA',                value: docBrief.mandatories,        type: 'list' },
    { title: 'GRAPHIC ASSET TYPE',                     value: docBrief.graphic_asset_type, type: 'text' },
    { title: 'BRANDING GUIDANCE',                      value: docBrief.branding_guidance,  type: 'list' },
    { title: 'KEY POINTS',                             value: docBrief.key_points,         type: 'list' },
    { title: 'ŹRÓDŁA',                                 value: docBrief.sources_summary,    type: 'text' },
  ].filter(s => s.value && (Array.isArray(s.value) ? s.value.length : String(s.value).trim()));

  const sectionsHtml = sections.map(s => `
    <div class="doc-section">
      <div class="doc-section-title">${s.title}</div>
      ${s.type === 'list'
        ? `<ul class="doc-list">${listHtml(safeList(s.value))}</ul>`
        : `<p class="doc-body">${safe(s.value)}</p>`}
    </div>`).join('');

  const badgeWorkflowHtml = currentBadgeGeneration
    ? renderBadgeGenerationMarkup(currentBadgeGeneration, currentBadgeDownloadUrl)
    : `
      <div class="badge-workflow">
        <div class="badge-workflow-head">
          <div>
            <div class="doc-section-title">Następny krok</div>
            <div class="badge-workflow-title">Akceptuj brief, aby uruchomić generowanie badge'y</div>
          </div>
          <span class="badge-status-pill waiting">oczekuje</span>
        </div>
        <p class="badge-workflow-copy">
          Po akceptacji uruchomię generowanie wariantów badge'y zgodnych z brandbookiem Accenture
          i pokażę gotowe pliki oraz statusy renderowania.
        </p>
        <div class="badge-upload-box">
          <label class="badge-upload-label" for="badge-participants-file">Lista uczestników (.xlsx)</label>
          <input class="badge-upload-input" id="badge-participants-file" type="file" accept=".xlsx">
          <div class="badge-upload-hint">
            Opcjonalnie dodaj Excel z kolumnami typu: Imię i nazwisko, Firma, Stanowisko, Rola na konferencji.
            Jeśli plik nie zostanie dodany, system wygeneruje przykładowe warianty per typ uczestnika.
          </div>
        </div>
      </div>`;

  content.innerHTML = `
    <div class="doc-preview">
      ${badgeWorkflowHtml}
      <div class="doc-inner">
        <div class="doc-title">${safe(docBrief.title || 'BRIEF NA KAMPANIĘ')}</div>
        ${sectionsHtml}
      </div>
    </div>`;

  content.scrollTop = 0;
  panel.scrollTop   = 0;
}

function renderBadgeGenerationMarkup(badgeGeneration, artifactDownloadUrl) {
  const badges = Array.isArray(badgeGeneration?.badges) ? badgeGeneration.badges : [];
  const summary = badgeGeneration?.summary || {};
  const workflowStatus = String(badgeGeneration?.status || 'started');
  const workflowStatusClass = workflowStatus.includes('fail') ? 'failed' : 'started';

  const itemsHtml = badges.map(badge => `
    <div class="badge-plan-item">
      <div class="badge-plan-meta">
        <div class="badge-plan-name">${escapeHtml(badge.name || 'Badge')}</div>
        <span class="badge-status-pill ${String(badge.status || '').includes('fail') ? 'failed' : 'started'}">${escapeHtml(badge.status || 'started')}</span>
      </div>
      <div class="badge-plan-goal">${escapeHtml(badge.visual_cue || '')}</div>
      <div class="badge-plan-copy"><strong>Typ uczestnika:</strong> ${escapeHtml(badge.participant_type || '—')}</div>
      <div class="badge-plan-copy"><strong>Przykładowe dane:</strong> ${escapeHtml([
        badge.sample_participant?.first_name,
        badge.sample_participant?.last_name,
        badge.sample_participant?.company,
        badge.sample_participant?.position,
      ].filter(Boolean).join(' / ') || '—')}</div>
      <div class="badge-plan-copy"><strong>Brandbook:</strong> ${escapeHtml(
        badge.badgeLayoutData?.branding?.brandbookSource || badge.brandbook_source || badgeGeneration?.summary?.brandbook_source || 'Brand guidelines'
      )}</div>
      <div class="badge-plan-prompt"><strong>Background prompt:</strong> ${escapeHtml(badge.backgroundPrompt || '—')}</div>
      <div class="badge-plan-prompt"><strong>Negative prompt:</strong> ${escapeHtml(badge.negativePrompt || '—')}</div>
      <div class="badge-plan-prompt"><strong>Deterministic layout:</strong> ${escapeHtml([
        badge.badgeLayoutData?.conferenceName,
        badge.badgeLayoutData?.participant?.participantType,
        badge.badgeLayoutData?.participant?.firstName,
        badge.badgeLayoutData?.participant?.lastName,
      ].filter(Boolean).join(' / ') || '—')}</div>
      ${badge.preview_url
        ? `<div class="badge-plan-image-wrap"><img class="badge-plan-image" src="${badge.preview_url}" alt="${escapeHtml(badge.name || 'Badge preview')}"></div>`
        : ''}
      ${badge.error ? `<div class="badge-plan-error">${escapeHtml(badge.error)}</div>` : ''}
      <div class="badge-workflow-actions">
        ${badge.download_url
          ? `<a class="btn btn-primary btn-sm" href="${badge.download_url}" download>↓ ${escapeHtml((badge.format || 'png').toUpperCase())}</a>`
          : ''}
      </div>
    </div>`).join('');

  return `
    <div class="badge-workflow">
      <div class="badge-workflow-head">
        <div>
          <div class="doc-section-title">Badge workflow</div>
          <div class="badge-workflow-title">Proces generowania badge'y został uruchomiony</div>
        </div>
        <span class="badge-status-pill ${workflowStatusClass}">${escapeHtml(workflowStatus)}</span>
      </div>
      <p class="badge-workflow-copy">
        ${escapeHtml(badgeGeneration?.message || 'Szkielet procesu został uruchomiony.')}
        ${summary.generated_count != null ? ` Wygenerowano ${summary.generated_count} z ${summary.variants_count || badges.length} wariantów.` : ''}
        ${summary.participants_count ? ` Lista uczestników zawiera ${summary.participants_count} pozycji.` : ''}
      </p>
      <div class="badge-upload-box">
        <label class="badge-upload-label" for="badge-participants-file">Lista uczestników (.xlsx)</label>
        <input class="badge-upload-input" id="badge-participants-file" type="file" accept=".xlsx">
        <div class="badge-upload-hint">
          Dodaj nowy Excel i użyj „Generuj ponownie", jeśli chcesz przygotować badge'e dla innej listy uczestników.
        </div>
      </div>
      <div class="badge-plan-grid">
        ${itemsHtml || '<div class="badge-plan-item"><div class="badge-plan-name">Brak wariantów badge\'y.</div></div>'}
      </div>
      <div class="badge-workflow-actions">
        ${artifactDownloadUrl ? `<a class="btn btn-primary btn-sm" href="${artifactDownloadUrl}" download>↓ JSON</a>` : ''}
      </div>
    </div>`;
}

async function acceptDocumentBrief(btn) {
  if (!currentDocumentBrief) return;

  const statusEl = document.getElementById('brief-panel-status');
  const participantFile = document.getElementById('badge-participants-file')?.files?.[0] || null;
  const original = btn.textContent;

  btn.disabled = true;
  btn.textContent = 'Uruchamiam…';
  statusEl.textContent = "Trwa uruchamianie procesu generowania badge'y\u2026";
  statusEl.style.color = 'var(--gray-dark)';
  statusEl.style.display = 'block';

  try {
    const formData = new FormData();
    formData.append('brief', JSON.stringify(currentBrief));
    formData.append('document_brief', JSON.stringify(currentDocumentBrief));
    formData.append('sources', JSON.stringify(currentSources || []));
    formData.append('format', 'png');
    if (participantFile) {
      formData.append('participants_file', participantFile);
    }

    const res  = await fetch('/generate_badges', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok || data.error) {
      const detail = data.error ? ` (${data.error})` : '';
      statusEl.textContent = `Błąd: Nie udało się uruchomić badge'y${detail}.`;
      statusEl.style.color = '#c00';
      btn.disabled = false;
      btn.textContent = original;
      return;
    }

    currentBadgeGeneration  = data.badge_generation || null;
    currentBadgeDownloadUrl = data.download_url || '';
    statusEl.style.display  = 'none';
    renderDocumentPreview(currentDocumentBrief, currentDocumentDownloadUrl);
    addAIMessage("Brief został zaakceptowany. Zakończyłam próbę wygenerowania wariantów badge'y i dodałam wyniki do panelu.", false);
    showToast("Badge'e przetworzone");

  } catch (err) {
    statusEl.textContent = `Błąd połączenia: ${err.message}`;
    statusEl.style.color = '#c00';
    btn.disabled = false;
    btn.textContent = original;
  }
}

async function downloadAsPdf(btn) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generuję…';

  try {
    const res = await fetch('/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: currentBrief,
        sources: currentSources,
        combined_text: currentCombinedText,
        format: 'pdf',
      }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      btn.textContent = 'Błąd';
      setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);
      return;
    }

    // Trigger browser download
    const a = document.createElement('a');
    a.href = data.download_url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();

    btn.textContent = 'Pobrano ✓';
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);

  } catch (err) {
    btn.textContent = 'Błąd';
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);
  }
}

function returnToBriefView() {
  const panelStatus = document.getElementById('brief-panel-status');
  if (panelStatus) panelStatus.style.display = 'none';
  briefPanelMode = 'brief';
  renderBriefPanelHeader();
  renderBriefPanel();
}
