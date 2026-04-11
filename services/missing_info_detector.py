from services.brief_schema import FIELD_RULES

GENERIC_VALUES = {
    "n/a",
    "none",
    "unknown",
    "not provided",
    "brak",
    "nie podano",
    "null"
}

AMBIGUOUS_VALUES = {
    "all",
    "everyone",
    "general",
    "online",
    "social media",
    "good results",
    "młodzi ludzie",
    "wszyscy",
    "internet",
    "dobre wyniki"
}

def evaluate_string(value):
    if value is None:
        return "missing"

    if not isinstance(value, str):
        return "missing"

    cleaned = value.strip().lower()

    if cleaned == "":
        return "missing"

    if cleaned in GENERIC_VALUES:
        return "missing"

    if cleaned in AMBIGUOUS_VALUES:
        return "ambiguous"

    if len(cleaned) < 3:
        return "ambiguous"

    return "present"

def evaluate_list(value):
    if value is None:
        return "missing"

    if not isinstance(value, list):
        return "missing"

    if len(value) == 0:
        return "missing"

    cleaned_items = [str(item).strip().lower() for item in value if str(item).strip()]

    if len(cleaned_items) == 0:
        return "missing"

    if len(cleaned_items) == 1 and cleaned_items[0] in AMBIGUOUS_VALUES:
        return "ambiguous"

    return "present"

def detect_missing_fields(brief_json: dict) -> list:
    results = []

    for field_name, meta in FIELD_RULES.items():
        value = brief_json.get(field_name)
        field_type = meta["type"]

        if field_type == "string":
            status = evaluate_string(value)
        elif field_type == "list":
            status = evaluate_list(value)
        else:
            status = "missing"

        if status in ["missing", "ambiguous"]:
            results.append({
                "field": field_name,
                "label": meta["label"],
                "status": status,
                "current_value": value,
                "question": meta["question"]
            })

    return results