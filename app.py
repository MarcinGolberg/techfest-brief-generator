from flask import Flask, request, render_template, Response
import json
import os
import re
import uuid
from werkzeug.utils import secure_filename

from services.brief_pipeline import analyze_inputs
from services.missing_info_detector import detect_missing_fields
from services.brief_schema import FIELD_RULES
from services.chat_agent import validate_and_process_answer

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

@app.route("/chat_answer", methods=["POST"])
def chat_answer():
    try:
        data = request.get_json()
        brief               = data["brief"]
        field               = data["field"]
        conversation_history = data["conversation_history"]   # [{role, content}, ...]

        field_meta  = FIELD_RULES.get(field, {})
        field_label = field_meta.get("label", field)
        field_type  = field_meta.get("type", "string")
        question    = field_meta.get("question", "")

        result = validate_and_process_answer(
            field_label=field_label,
            field_type=field_type,
            question=question,
            conversation_history=conversation_history,
            brief_context=brief,
        )

        status = result.get("status", "needs_more")

        if status == "accepted":
            raw_value = result.get("brief_value") or ""
            if field_type == "list":
                items = re.split(r"[,;\n]+", raw_value)
                brief[field] = [item.strip() for item in items if item.strip()]
            else:
                brief[field] = raw_value.strip()

            missing_fields = detect_missing_fields(brief)
            return Response(
                json.dumps({
                    "status": "accepted",
                    "response": result.get("response", ""),
                    "brief": brief,
                    "missing_fields": missing_fields,
                }, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
            )

        # needs_more or invalid — no brief update, just return the follow-up
        return Response(
            json.dumps({
                "status": status,
                "response": result.get("response", ""),
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status=500,
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