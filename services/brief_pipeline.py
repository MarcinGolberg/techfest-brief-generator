import json
from file_parser import BriefInputParser
from services.ai_service import extract_brief_from_text
from services.missing_info_detector import detect_missing_fields

def analyze_inputs(raw_texts=None, file_paths=None):
    parser = BriefInputParser()

    payload_str = parser.generate_json_payload(
        raw_texts=raw_texts or [],
        file_paths=file_paths or [],
        save_to_file=False
    )

    payload = json.loads(payload_str)
    combined_text = payload.get("combined_text", "")

    if not combined_text.strip():
        raise ValueError("No input text found after parsing.")

    raw_ai_response = extract_brief_from_text(combined_text)

    cleaned_response = raw_ai_response.strip()

    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response.removeprefix("```json").strip()

    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response.removeprefix("```").strip()

    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response.removesuffix("```").strip()

    try:
        brief_json = json.loads(cleaned_response)
    except json.JSONDecodeError:
        raise ValueError(f"Model returned invalid JSON: {raw_ai_response}")

    missing_fields = detect_missing_fields(brief_json)

    return {
        "sources": payload.get("sources", []),
        "combined_text": combined_text,
        "brief": brief_json,
        "missing_fields": missing_fields
    }