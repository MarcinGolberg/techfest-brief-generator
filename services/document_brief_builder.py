import json
from services.ai_service import extract_structured_text

def build_document_brief(brief: dict, sources: list, combined_text: str) -> dict:
    with open("prompts/enrich_brief.txt", "r", encoding="utf-8") as f:
        template = f.read()

    prompt = (
        template
        .replace("{{brief_json}}", json.dumps(brief, ensure_ascii=False, indent=2))
        .replace("{{sources_json}}", json.dumps(sources, ensure_ascii=False, indent=2))
        .replace("{{combined_text}}", combined_text or "")
    )

    raw_response = extract_structured_text(prompt)
    cleaned = raw_response.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(f"Model zwrócił niepoprawny JSON dla document brief: {raw_response}")