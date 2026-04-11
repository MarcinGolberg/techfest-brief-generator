from flask import Flask, request, render_template, Response, send_from_directory
import json
import os
import re
import uuid
from werkzeug.utils import secure_filename

from services.brief_pipeline import analyze_inputs
from services.missing_info_detector import detect_missing_fields
from services.brief_schema import FIELD_RULES
from services.chat_agent import validate_and_process_answer
from services.document_brief_builder import build_document_brief
from services.brief_generator import generate_brief_file

app = Flask(__name__)
app.json.ensure_ascii = False

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)


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

        brief = data["brief"]
        field = data["field"]
        conversation_history = data["conversation_history"]

        field_meta = FIELD_RULES.get(field, {})
        field_label = field_meta.get("label", field)
        field_type = field_meta.get("type", "string")
        question = field_meta.get("question", "")

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
                    "missing_fields": missing_fields
                }, ensure_ascii=False),
                mimetype="application/json; charset=utf-8"
            )

        return Response(
            json.dumps({
                "status": status,
                "response": result.get("response", "")
            }, ensure_ascii=False),
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
            json.dumps({
                "brief": brief,
                "missing_fields": missing_fields
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        )

    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status=500
        )


@app.route("/finalize", methods=["POST"])
def finalize():
    try:
        data = request.get_json()

        if not data:
            return Response(
                json.dumps({"error": "Brak body JSON"}, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
                status=400
            )

        brief = data.get("brief", {})
        sources = data.get("sources", [])
        combined_text = data.get("combined_text", "")
        file_format = data.get("format", "docx").strip().lower()

        if not brief:
            return Response(
                json.dumps({"error": "Brak pola brief"}, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
                status=400
            )

        missing_fields = detect_missing_fields(brief)
        if missing_fields:
            return Response(
                json.dumps({
                    "error": "Brief nadal ma brakujące pola",
                    "missing_fields": missing_fields
                }, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
                status=400
            )

        document_brief = build_document_brief(
            brief=brief,
            sources=sources,
            combined_text=combined_text
        )

        file_path = generate_brief_file(
            brief=document_brief,
            file_format=file_format,
            output_dir=GENERATED_FOLDER
        )

        filename = os.path.basename(file_path)

        return Response(
            json.dumps({
                "message": "Document brief i plik zostały wygenerowane",
                "document_brief": document_brief,
                "file_path": file_path,
                "download_url": f"/download-generated/{filename}",
                "format": file_format
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        )

    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
            status=500
        )


@app.route("/download-generated/<filename>", methods=["GET"])
def download_generated(filename):
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True)