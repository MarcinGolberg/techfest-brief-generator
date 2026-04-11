// ── Composer — file upload, drag-drop, char counter, submit ──────────────────

const textarea   = document.getElementById('msg');
const charCount  = document.getElementById('char-count');
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const uploadBtn  = document.getElementById('btn-upload');
const submitBtn  = document.getElementById('btn-submit');
const resultBox  = document.getElementById('result-box');

const MAX = 2000;
let selectedFiles = [];
let dragCounter   = 0;

// ── Character counter ─────────────────────────────────────────────────────────
textarea.addEventListener('input', () => {
  const n = textarea.value.length;
  charCount.textContent = `${n.toLocaleString()} / ${MAX.toLocaleString()}`;
  charCount.classList.toggle('warn',  n >= MAX * 0.8 && n < MAX);
  charCount.classList.toggle('limit', n >= MAX);
});

// ── Drop zone label ───────────────────────────────────────────────────────────
function updateDropZoneLabel() {
  if (selectedFiles.length === 0) {
    dropZone.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="square">
        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19
                 a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
      </svg>
      Przeciągnij pliki tutaj albo użyj przycisku poniżej`;
    return;
  }
  const names = selectedFiles.map(f => f.name).join(', ');
  dropZone.textContent = `Wybrane pliki (${selectedFiles.length}): ${names}`;
}

// ── File input ────────────────────────────────────────────────────────────────
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  selectedFiles = Array.from(fileInput.files);
  updateDropZoneLabel();
  if (selectedFiles.length) showToast(`Dodano ${selectedFiles.length} plik(ów)`);
});

// ── Drag & drop ───────────────────────────────────────────────────────────────
document.addEventListener('dragenter', (e) => {
  if (e.dataTransfer.types.includes('Files')) {
    dragCounter++;
    dropZone.classList.add('drag-over');
  }
});

document.addEventListener('dragleave', () => {
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    dropZone.classList.remove('drag-over');
  }
});

document.addEventListener('dragover', (e) => e.preventDefault());

document.addEventListener('drop', (e) => {
  e.preventDefault();
  dragCounter = 0;
  dropZone.classList.remove('drag-over');

  const files = Array.from(e.dataTransfer.files || []);
  if (files.length) {
    selectedFiles = files;
    updateDropZoneLabel();
    showToast(`Dodano ${files.length} plik(ów)`);
  }
});

// ── Submit ────────────────────────────────────────────────────────────────────
submitBtn.addEventListener('click', async () => {
  const message = textarea.value.trim();

  if (!message && selectedFiles.length === 0) {
    showToast('Dodaj wiadomość albo co najmniej jeden plik');
    textarea.focus();
    return;
  }

  submitBtn.disabled    = true;
  submitBtn.textContent = 'Wysyłanie...';

  try {
    const formData = new FormData();
    formData.append('message', message);
    selectedFiles.forEach(file => formData.append('files', file));

    const response = await fetch('/analyze', { method: 'POST', body: formData });
    const data     = await response.json();

    if (!response.ok) {
      resultBox.style.display = 'block';
      resultBox.textContent   = JSON.stringify(data, null, 2);
      showToast('Błąd podczas generowania briefu');
      return;
    }

    startChatMode(data);
    showToast('Brief wygenerowany');

  } catch (error) {
    resultBox.style.display = 'block';
    resultBox.textContent   = `Błąd: ${error.message}`;
    showToast('Błąd połączenia z backendem');
  } finally {
    submitBtn.disabled    = false;
    submitBtn.textContent = 'Submit >';
  }
});
