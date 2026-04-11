import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from file_parser import BriefInputParser

parser = BriefInputParser()

result = parser.generate_json_payload(
    raw_texts=[],
    file_paths=[
        "tests/przyklad-brief.eml"
    ],
    save_to_file=False
)

print(result)