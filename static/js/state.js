// ── Brief schema (mirrors FIELD_RULES in brief_schema.py) ────────────────────
const BRIEF_SCHEMA = [
  { field: 'campaign_goal',       label: 'Cel kampanii',            type: 'string' },
  { field: 'product_or_service',  label: 'Produkt lub usługa',      type: 'string' },
  { field: 'target_audience',     label: 'Grupa docelowa',          type: 'string' },
  { field: 'key_messages',        label: 'Kluczowe komunikaty',     type: 'list'   },
  { field: 'marketing_channels',  label: 'Kanały marketingowe',     type: 'list'   },
  { field: 'tone_of_voice',       label: 'Ton komunikacji',         type: 'string' },
  { field: 'kpis',                label: 'KPI',                     type: 'list'   },
  { field: 'success_measurement', label: 'Ocena sukcesu',           type: 'string' },
  { field: 'scope_of_work',       label: 'Zakres działań',          type: 'string' },
  { field: 'client_expectations', label: 'Oczekiwania klienta',     type: 'string' },
];

// ── Mutable application state ─────────────────────────────────────────────────
let currentBrief            = null;
let currentMissing          = [];
let currentSources          = [];
let currentCombinedText     = '';
let currentDocumentBrief    = null;
let currentDocumentDownloadUrl = '';
let currentBadgeGeneration  = null;
let currentBadgeDownloadUrl = '';
let briefPanelMode          = 'brief'; // 'brief' | 'document'
let fieldConversation       = [];      // [{role, content}] for the current field only
let invalidStreak           = 0;       // consecutive "invalid" AI responses for current field
let chatMode                = 'filling'; // 'filling' | 'editing'
