from flask import Flask, request, render_template, Response
import json
import os
import re
import uuid
from werkzeug.utils import secure_filename

from services.brief_pipeline import analyze_inputs
from services.missing_info_detector import detect_missing_fields
from services.brief_schema import FIELD_RULES

app = Flask(__name__)
app.json.ensure_ascii = False

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        raw_message = request.form.get("message", "").strip()
        uploaded_files = request.files.getlist("files")

        saved_file_paths = []

        for file in uploaded_files:
            if not file or not file.filename:
                continue

            original_name = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex}_{original_name}"
            save_path = os.path.join(UPLOAD_FOLDER, unique_name)
            file.save(save_path)
            saved_file_paths.append(save_path)

        result = analyze_inputs(
            raw_texts=[raw_message] if raw_message else [],
            file_paths=saved_file_paths
        )

        return Response(
            json.dumps(result, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        )

    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status=500
        )

@app.route("/update_brief", methods=["POST"])
def update_brief():
    try:
        data = request.get_json()
        brief = data["brief"]
        field = data["field"]
        answer = data["answer"]

        field_type = FIELD_RULES.get(field, {}).get("type", "string")

        if field_type == "list":
            items = re.split(r"[,;\n]+", answer)
            brief[field] = [item.strip() for item in items if item.strip()]
        else:
            brief[field] = answer.strip()

        missing_fields = detect_missing_fields(brief)

        return Response(
            json.dumps({"brief": brief, "missing_fields": missing_fields}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        )

    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status=500
        )


if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True)