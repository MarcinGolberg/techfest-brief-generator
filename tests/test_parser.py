import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from file_parser import BriefInputParser

EML = os.path.join(os.path.dirname(__file__), "przyklad-brief.eml")

parser = BriefInputParser()

assert os.path.exists(EML), f"fixture missing: {EML}"

result = parser.generate_json_payload(
    raw_texts=[],
    file_paths=[EML],
    save_to_file=False
)

payload = json.loads(result)
text = payload["combined_text"]

# The header is RFC 2047 encoded and the body is windows-1250 quoted-printable
# nested two levels deep, so these three assertions cover the whole decode path.
assert "wiosenna kampania księgarni" in text, "RFC 2047 subject did not decode"
assert "Czytaj taniej, myśl drożej" in text, "windows-1250 body did not decode"
assert "<html>" not in text, "the text/html part leaked into the payload"

print(result)
print("OK")
