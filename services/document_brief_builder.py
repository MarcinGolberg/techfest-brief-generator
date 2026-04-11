import json
import os
from services.ai_service import extract_structured_text, strip_code_fences

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

def build_document_brief(brief: dict, sources: list, combined_text: str) -> dict:
    with open(os.path.join(_PROMPTS_DIR, "enrich_brief.txt"), "r", encoding="utf-8") as f:
        template = f.read()

    prompt = (
        template
        .replace("{{brief_json}}", json.dumps(brief, ensure_ascii=False, indent=2))
        .replace("{{sources_json}}", json.dumps(sources, ensure_ascii=False, indent=2))
        .replace("{{combined_text}}", combined_text or "")
    )

    raw_response = extract_structured_text(prompt)
    cleaned = strip_code_fences(raw_response)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(f"Model zwrócił niepoprawny JSON dla document brief: {raw_response}")