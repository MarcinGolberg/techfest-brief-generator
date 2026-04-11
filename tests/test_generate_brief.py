import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from file_parser import BriefInputParser
from services.ai_service import extract_brief_from_text

BASE_DIR = os.path.dirname(__file__)
email_file = os.path.join(BASE_DIR, "przyklad-brief.eml")

parser = BriefInputParser()

payload_str = parser.generate_json_payload(
    raw_texts=[],
    file_paths=[email_file],
    save_to_file=False
)

payload = json.loads(payload_str)
combined_text = payload["combined_text"]

print("=== COMBINED TEXT ===")
print(combined_text[:3000])

raw_ai_response = extract_brief_from_text(combined_text)

print("\n=== RAW AI RESPONSE ===")
print(raw_ai_response)