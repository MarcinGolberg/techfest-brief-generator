# Accenture TechFest 3.0 — Team 4

AI-powered marketing brief generator and conference badge creator, built for the Accenture TechFest 3.0 hackathon.

---

## Running the application

### Prerequisites

- Python 3.11+
- Azure LLM credentials (see Environment variables below)

### Environment variables

```
AZURE_LLM_ENDPOINT=<Azure OpenAI endpoint URL>
AZURE_LLM_API_KEY=<Azure OpenAI API key>
AZURE_LLM_API_VERSION=<e.g. 2024-02-01>
AZURE_LLM_DEPLOYMENT=<chat model deployment name>
AZURE_IMAGE_DEPLOYMENT=<image model deployment name>

# Optional — dedicated embedding deployment for badge tone detection
# Falls back to AZURE_LLM_ENDPOINT / AZURE_LLM_API_KEY if not set
AZURE_EMBEDDING_ENDPOINT=<Azure OpenAI endpoint for embeddings>
AZURE_EMBEDDING_API_KEY=<Azure OpenAI API key for embeddings>
AZURE_EMBEDDING_DEPLOYMENT=<embedding model name, e.g. text-embedding-3-large>

# Optional — enables FLUX image generation instead of Azure OpenAI Images
FLUX_API_ENDPOINT=<BFL API endpoint>
FLUX_API_KEY=<BFL API key>
```

### Local

```bash
pip install -r requirements.txt
python app.py
```

### Docker

```bash
docker build -t team4-app .
docker run -p 5000:5000 --env-file .env team4-app
```

### Deployed image

```
acrtf3team04.azurecr.io/team4-app:latest
```

Azure App Service URL: `https://accenturebrief.azurewebsites.net`

---

## Application flow

### High-level pipeline

```
User input (text / files)
        │
        ▼
   File parsing          ← file_parser.py: PDF, DOCX, PPTX, EML, XLSX → combined_text
        │
        ▼
  Brief extraction       ← AI call with extract_brief.txt prompt → raw JSON brief (10 fields)
        │
        ▼
  Missing field detection ← missing_info_detector.py → list of incomplete / ambiguous fields
        │
        ▼
  Chat Q&A loop          ← chat_agent.py: AI "Maja" validates each user answer field by field
        │
        ▼
  Brief complete          ← all 10 fields accepted
        │
        ├──▶  Brief editing  ← brief_editor.py: user types natural-language edits in chat
        │
        ▼
  Document brief generation ← enrich_brief.txt prompt → extended document-ready JSON
        │
        ├──▶  Export DOCX    ← brief_generator.py → brief_<uuid>.docx
        │
        ├──▶  Export PDF     ← brief_generator.py → brief_<uuid>.pdf
        │
        ▼
  Badge generation        ← badge_generator.py: deterministic PIL layout + AI background image
        │
        ▼
  Badge export            ← badge_<uuid>_<role>.png/jpg per participant type
```

### Step-by-step user path

| Step | What the user does | What the system does |
|------|--------------------|----------------------|
| 1 | Types a description of their campaign and/or uploads files (PDF, DOCX, PPTX, EML, XLSX) | `file_parser.py` extracts text from each file; all sources are merged into `combined_text` |
| 2 | Clicks **Submit** | `brief_pipeline.py` sends the combined text to the LLM with the `extract_brief.txt` prompt; the response is parsed into a 10-field JSON brief |
| 3 | The chat overlay opens | `missing_info_detector.py` checks each field for empty, generic, or ambiguous values and returns a prioritised list |
| 4 | Answers Maja's questions one by one | `chat_agent.py` evaluates each answer (accepted / needs\_more / invalid); on acceptance the field is written into the brief and the sidebar + panel update live |
| 5 | After two consecutive nonsense answers | A manual input card appears so the user can type directly without the AI validation loop |
| 6 | All 10 fields filled | The chat switches to **edit mode**: the user can type natural-language commands like *"Change the target audience to women 25–40"* |
| 7 | Clicks **Generate document** | `document_brief_builder.py` enriches the brief with the `enrich_brief.txt` prompt; the result is rendered as a document preview in the right panel |
| 8 | Downloads DOCX or PDF | `brief_generator.py` writes the document via `python-docx` or `reportlab` and serves it |
| 9 | Clicks **Accept brief** | `badge_generator.py` generates one badge per participant role (or per row in an uploaded `.xlsx`); each badge uses a PIL-drawn layout with an AI-generated background |
| 10 | Downloads individual badge images or the summary JSON | Files are served from the `generated/` folder via `/download-generated/<filename>` |

---

## How prompts are used

The application has four prompts. Two live in the `prompts/` directory as plain text files that are read at runtime and have `{{placeholder}}` variables substituted before being sent to the model. The other two are Python string constants (`SYSTEM_PROMPT`, `EDIT_SYSTEM_PROMPT`) defined directly inside their service files, which makes them part of the code rather than external assets.

| # | Prompt | Location | Loaded as |
|---|--------|----------|-----------|
| 1 | Brief extraction | `prompts/extract_brief.txt` | File read + `{{input_text}}` substitution |
| 2 | Answer validation (Maja) | `services/chat_agent.py` → `SYSTEM_PROMPT` | Inline Python constant |
| 3 | Brief enrichment | `prompts/enrich_brief.txt` | File read + three `{{…}}` substitutions |
| 4 | Brief editing | `services/brief_editor.py` → `EDIT_SYSTEM_PROMPT` | Inline Python constant |

### 1. Brief extraction — `prompts/extract_brief.txt`

**When:** immediately after the user submits their input (step 2 above).

**What it does:** The prompt instructs the model to act as a structured information extraction system. It receives the full `combined_text` (all uploaded files and typed text merged) and must return a single valid JSON object with exactly 10 fields:

| Field | Type | Description |
|-------|------|-------------|
| `campaign_goal` | string | Why the campaign is being run |
| `product_or_service` | string | What is being promoted |
| `target_audience` | string | Who the campaign targets |
| `key_messages` | list | Core messages / value propositions |
| `marketing_channels` | list | Where the campaign will run |
| `tone_of_voice` | string | Communication style |
| `kpis` | list | Measurable success indicators |
| `success_measurement` | string | How success is judged qualitatively |
| `scope_of_work` | string | What deliverables are in scope |
| `client_expectations` | string | Client constraints and preferences |

**Key rules embedded in the prompt:**
- Extract **only** what is explicitly stated — no inference or guessing.
- Missing fields return `""` (strings) or `[]` (lists), never invented values.
- Language follows the input: Polish input → Polish output.
- Normalise content: remove duplicates, condense to concise phrases.

**How the response is used:** `brief_pipeline.py` calls `strip_code_fences()` to remove any markdown wrappers, then `json.loads()` to parse the result. The parsed dict goes straight into `detect_missing_fields()`.

---

### 2. Answer validation — `SYSTEM_PROMPT` in `services/chat_agent.py`

**When:** every time the user sends a message during the Q&A filling phase (step 4).

**What it does:** The model plays the role of **Maja**, a senior marketing consultant. She evaluates the user's latest answer in the context of the specific brief field being filled and classifies it as one of three statuses:

| Status | Meaning | Action |
|--------|---------|--------|
| `accepted` | Answer is concrete and appropriate | Field is written to the brief; move to the next missing field |
| `needs_more` | Answer is understandable but too vague | Maja asks a follow-up; `invalidStreak` resets to 0 |
| `invalid` | Answer is nonsense / random characters | Maja signals confusion; `invalidStreak` increments. After 2 consecutive invalids the manual input card appears |

**How the context is structured:** `chat_agent.py` assembles a single user-turn message containing:
- The current field label and type (string vs list)
- The original question for this field
- The current values of `product_or_service` and `target_audience` from the brief (so Maja has context)
- The full conversation history for this specific field (`fieldConversation` in JS, `conversation_history` in the API call)

The model is told to return **only valid JSON** (`response_format={"type": "json_object"}`), with exactly three keys: `status`, `brief_value`, and `response` (a warm Polish message shown to the user).

**Why per-field conversation history:** Each field resets `fieldConversation` to `[]` when a new question starts. This keeps the context window short and prevents the model from being confused by answers to previous fields.

---

### 3. Brief enrichment — `prompts/enrich_brief.txt`

**When:** when the user clicks **Generate document** (step 7).

**What it does:** The prompt takes the completed 10-field brief JSON, the list of original sources, and the full `combined_text`, and asks the model to transform them into an **extended document-ready JSON** with 13 fields suitable for a professional marketing brief document:

| Field | Contents |
|-------|---------|
| `title` | Document title |
| `executive_summary` | Short summary for quick reading |
| `background` | Context and project description |
| `objective` | Campaign goal in document language |
| `target_group` | Audience in document language |
| `issue` | Business problem being addressed |
| `insight` | Key insight motivating the campaign |
| `creative_challenge` | The creative problem to solve |
| `mandatories` | Constraints and requirements (list) |
| `graphic_asset_type` | Type of visual output expected |
| `branding_guidance` | Brand rules to follow (list) |
| `key_points` | Most important take-aways (list) |
| `sources_summary` | Description of all input sources used |

**Key rules embedded in the prompt:**
- Use Polish throughout.
- Use only provided input — do not invent unsupported facts.
- `mandatories`, `branding_guidance`, and `key_points` must always be arrays.
- If a value is missing keep it concise and neutral rather than fabricating.

**How the response is used:** `document_brief_builder.py` strips code fences and parses the JSON. The result is stored as `currentDocumentBrief` in the browser and rendered in the right panel. It is also passed to `brief_generator.py` to produce the DOCX/PDF file.

---

### 4. Brief editing — `EDIT_SYSTEM_PROMPT` in `services/brief_editor.py`

**When:** the user types a natural-language edit command during edit mode (step 6), e.g. *"Change the target audience to women aged 25–40"*.

**What it does:** The model receives the full current brief JSON and the user's edit instruction, and returns only the fields that need to change, plus a short Polish confirmation message.

**Response format:**
```json
{
  "updated_fields": {
    "target_audience": "Kobiety w wieku 25–40 lat"
  },
  "response": "Gotowe! Zaktualizowałam grupę docelową."
}
```

The server merges only the returned fields back into the brief, re-runs `detect_missing_fields()`, and flashes each updated field in the UI. If the edit invalidates any previously filled field (e.g. removes a required value), the flow automatically switches back to filling mode for those fields.

---

## Badge theming and tone detection

Every generated badge adapts its visual character to the conference brief through a two-stage pipeline: **conference theme detection** followed by **tone scoring**, which together produce a single resolved palette used for gradient rendering.

### Conference theme detection

`_detect_conference_theme()` scores each theme's keyword list against the brief text and returns the best match.

| Theme ID | Domain | Examples |
|----------|--------|---------|
| `tech_innovative` | Technology, AI, software | startup, cloud, blockchain, machine learning |
| `finance_formal` | Finance, banking, compliance | equity, audit, treasury, regulatory |
| `healthcare` | Medical, pharma, life science | clinical, biotech, genomics, patient |
| `marketing_creative` | Brand, advertising, media | campaign, storytelling, content, agency |
| `general` | Default fallback | — |

### Tone detection — embedding axis projection

`_detect_tone()` returns a continuous score **0.0 (very corporate) → 1.0 (very playful)** using semantic embedding projection:

1. Two sets of short, extreme anchor phrases define the poles of the tone axis (seriousness and playfulness).
2. The centroid of each set is computed once per process and cached.
3. A unit vector is derived from `playfulness_centroid − seriousness_centroid` — this is the **tone axis**.
4. The brief embedding is projected onto this axis.
5. The projection is calibrated using the anchor centroids as reference points (0 = serious pole, 1 = playful pole).

This is more discriminative than comparing independent cosine similarities because it measures movement along the specific tone dimension rather than overall proximity to either pole in the full high-dimensional space.

**Inputs for tone detection:**

| Source | Fields used | Why |
|--------|-------------|-----|
| Raw brief | `tone_of_voice`, `client_expectations`, `target_audience`, `campaign_goal` | Direct user declarations of character — highest signal quality; LLM enrichment tends to normalise these into neutral prose |
| Document brief | `title`, `executive_summary`, `target_group`, `insight`, `creative_challenge`, `key_points` | Industry and context signals |

**Keyword fallback:** when the embedding service is unavailable, a weighted keyword count over the same fields is used. Polish-language tone words are included explicitly (e.g. `elegancki/stonowany` → corporate; `zabawowy/energiczny/krzykliwy` → playful).

**`tone_cap`:** some domains are structurally formal. Finance is hard-capped at 0.35 and healthcare at 0.70, regardless of the detected score.

### Warm / cold colour axis

The tone score drives a lerp between two palette variants per theme. The colour axis is:

| Tone | Direction | Visual character |
|------|-----------|-----------------|
| 0.0 — corporate | **Cold** — near-black with steel/navy undertones | Single barely-visible blob, no streaks, static |
| 1.0 — playful | **Warm** — oranges, ambers, hot pinks, reds | 5 large vivid blobs, high opacity, diagonal light streaks |

| Theme | Corporate palette | Playful palette |
|-------|-------------------|-----------------|
| Tech | Near-black cold blue | Molten orange → hot pink |
| Finance (cap 0.35) | Midnight near-black | Cold deep navy (stays cold; cap prevents warm) |
| Healthcare (cap 0.70) | Clinical dark teal | Amber → coral |
| Marketing | Dark aubergine | Fire orange → hot pink |
| General | Near-black | Warm orange → rose |

### Tone label in the UI

The resolved tone score is shown in the badge workflow panel under each badge variant:

```
Typ uczestnika: Klient
Przykładowe dane: Anna / Nowak / FinCorp / Director of Innovation
Ton i charakter badga: Korporacyjny — stonowane, zimne odcienie (0.12)
```

| Score range | Label |
|-------------|-------|
| 0.00 – 0.15 | Bardzo korporacyjny — zimna, statyczna paleta |
| 0.15 – 0.30 | Korporacyjny — stonowane, zimne odcienie |
| 0.30 – 0.45 | Zrównoważony — umiarkowany charakter |
| 0.45 – 0.60 | Dynamiczny — cieplejsze akcenty |
| 0.60 – 0.78 | Swobodny — żywe, ciepłe barwy |
| 0.78 – 1.00 | Bardzo swobodny — intensywne, gorące kolory |

### AI visual keyword agent

`_scan_brief_for_visual_keywords()` calls the LLM with a Polish instruction to extract 5–8 visual atmosphere descriptors from the brief (mood, energy level, metaphors). The descriptors are appended in English to the image-generation prompt so the AI-generated background texture reinforces the conference's character. Generic terms like "purple" or "gradient" are explicitly excluded.

---

## Requirements compliance

### Functional requirements

| # | Requirement | Status | Implementation |
|---|------------|--------|----------------|
| 1 | End-to-end process in a single solution | ✅ | Single Flask app covers input → extraction → Q&A → brief → badge |
| 2 | Accept input in multiple formats | ✅ | `file_parser.py` handles typed text, email text, PDF, DOCX, PPTX, EML, XLSX |
| 3 | Identify and fill missing information | ✅ | `missing_info_detector.py` + chat Q&A loop with AI validation |
| 4 | Generate standardised final brief | ✅ | 10-field JSON brief; exported as DOCX or PDF with professional layout |
| 5 | Generate conference badge | ✅ | `badge_generator.py`: 5 role variants, PNG/JPG output, Accenture branding |
| 6 | Coherent user flow | ✅ | Guided overlay: sidebar progress, live brief panel, smooth transitions |

### Functionality 1 — Brief generation

| # | Requirement | Status | Implementation |
|---|------------|--------|----------------|
| 1 | Accept marketing guidelines in various formats | ✅ | Text paste + file upload; `BriefInputParser` reads PDF, DOCX, PPTX, EML, XLSX |
| 2 | Analyse and structure content | ✅ | `extract_brief.txt` prompt extracts and maps content to 10 standardised fields |
| 3 | Generate standardised brief (goal, product, audience, messages, channels, tone, KPI, success) | ✅ | All 8 required fields plus `scope_of_work` and `client_expectations` |
| 4 | Identify missing information | ✅ | `missing_info_detector.py` flags empty, generic (`"n/a"`, `"brak"`) and ambiguous (`"wszyscy"`, `"internet"`) values |
| 5 | Human-in-the-loop verification | ✅ | AI chat agent "Maja" validates each answer; falls back to manual input card after 2 consecutive invalid answers |

### Functionality 2 — Badge generation

| # | Requirement | Status | Implementation |
|---|------------|--------|----------------|
| 1 | Generate badge from brief | ✅ | `start_badge_generation()` reads conference name, branding, and participant data from the brief |
| 2 | Accenture brandbook compliance | ✅ | `BRAND_GUIDELINES` constant encodes colour palette (`#4A4AFF`, `#000000`, `#FFFFFF`), sharp-corner geometry, logo placement rules, and source document reference |
| 3 | Multiple variants for different participant types | ✅ | 5 role variants: `guest`, `client`, `partner`, `organizer`, `speaker` — each with its own accent colour and visual cue |
| 4 | Output as JPG or PNG | ✅ | PIL renders the final image; format is configurable (`png` default, `jpg` supported) |
| 5 | Use image generation model | ✅ | `generate_image_bytes()` calls either FLUX via BFL API or Azure OpenAI Images to generate a branded background per badge |
| 6 | Conference-aware visual theming | ✅ | `badge_generator.py` detects domain (tech / finance / healthcare / marketing) and scores tone via embedding axis projection; gradient palette lerps between cold-corporate and warm-playful poles |

### Non-functional requirements

| # | Requirement | Status | Implementation |
|---|------------|--------|----------------|
| 1 | Run on Microsoft Azure | ✅ | Deployed to Azure App Service (`accenturebrief`); image published to `acrtf3team04.azurecr.io` |
| 2 | Python 3.x | ✅ | Python 3.11; Flask web framework |
| 3 | Open-source libraries only | ✅ | All dependencies are open-source (Flask, python-docx, reportlab, Pillow, pypdf, openpyxl, openai SDK) |
| 4 | Simple and intuitive interface | ✅ | Single-page app: composer → guided chat overlay → live brief panel → download |
| 5 | Error handling without losing progress | ✅ | Toast notifications for transient errors; state rollback on failed API calls (e.g. `submitManualInput` restores `prevBrief` on failure); chat errors shown inline |

### Security requirements

| # | Requirement | Status | Implementation |
|---|------------|--------|----------------|
| 1 | Code in GitHub repository | ✅ | `TechFestOrg/team4` |
| 2 | Responsible AI / guardrails | ✅ | Maja's system prompt explicitly scopes her role to marketing brief validation; `invalid` status rejects nonsense inputs; `GENERIC_VALUES` and `AMBIGUOUS_VALUES` sets block low-quality data from entering the brief |
| 3 | No sensitive data in repo | ✅ | All credentials loaded from environment variables / Azure Key Vault; `.env` not committed |
| 4 | Automatic vulnerability scan | ✅ | CI/CD pipeline runs **Bandit** (static Python analysis) + **Safety** (dependency CVEs) + **Trivy** (container image scan); pipeline fails on HIGH/CRITICAL findings; reports uploaded as artifacts |
| 5 | SBOM in CycloneDX format | ✅ | `cyclonedx-bom` generates `sbom.json` on every pipeline run; artifact uploaded to GitHub Actions and sent to **DependencyTrack** via API |
| 6 | Quality Gate (fail-fast) | ✅ | **SonarQube** scan runs on every push; pipeline fails if security rating drops below A, bugs > 0, duplicated lines > 5%, or hotspots unreviewed |

### Optional features implemented

| # | Feature | Implementation |
|---|---------|----------------|
| 3 | User brief editing | Edit mode after brief completion: natural-language commands update individual fields via `brief_editor.py` |
| 2 | Multiple material variants | 5 badge role variants generated in a single run; each has a distinct visual style and accent colour |

---

## Project structure

```
team4/
├── app.py                        # Flask routes
├── file_parser.py                # Multi-format document text extraction
├── prompts/                          # File-based prompts (read at runtime, {{placeholder}} substitution)
│   ├── extract_brief.txt             # Prompt 1 — extract 10-field brief from raw text
│   └── enrich_brief.txt             # Prompt 3 — expand brief into document-ready JSON
├── services/
│   ├── ai_service.py                 # Azure OpenAI + FLUX client wrappers
│   ├── brief_pipeline.py             # Orchestrates parsing + extraction + missing-field detection
│   ├── brief_schema.py               # FIELD_RULES: field metadata (label, type, question)
│   ├── missing_info_detector.py      # Evaluates each field: present / ambiguous / missing
│   ├── chat_agent.py                 # SYSTEM_PROMPT (inline) — Prompt 2: Maja validates answers
│   ├── brief_editor.py               # EDIT_SYSTEM_PROMPT (inline) — Prompt 4: natural-language editing
│   ├── document_brief_builder.py     # Loads enrich_brief.txt, substitutes vars, calls AI
│   ├── brief_generator.py        # Writes DOCX (python-docx) and PDF (reportlab)
│   └── badge_generator.py        # PIL badge layout + AI background generation
├── templates/
│   └── index.html                # Single-page HTML shell
├── static/
│   ├── css/                      # 10 CSS files (base, header, hero, composer, chat, …)
│   └── js/                       # 7 JS files (state, utils, chat-ui, chat-flow, brief-panel, composer, main)
├── images/
│   └── Accenture-logo.png        # Official logo used in badge generation
├── generated/                    # Runtime output: briefs, badges (auto-cleaned after 24 h)
└── .github/workflows/deploy.yml  # DevSecOps CI/CD pipeline
```
