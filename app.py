from flask import Flask, request, render_template, Response, send_from_directory
import json
import os
import uuid
from werkzeug.utils import secure_filename

from services.brief_pipeline import analyze_inputs
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
            json.dumps(
                {
                    "message": "Document brief i plik zostały wygenerowane",
                    "document_brief": document_brief,
                    "file_path": file_path,
                    "download_url": f"/download-generated/{filename}",
                    "format": file_format
                },
                ensure_ascii=False
            ),
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