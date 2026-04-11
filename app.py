from flask import Flask, request, render_template, Response, send_from_directory
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

from services.brief_pipeline import analyze_inputs
from services.missing_info_detector import detect_missing_fields
from services.brief_schema import FIELD_RULES
from services.chat_agent import validate_and_process_answer
from services.document_brief_builder import build_document_brief
from services.brief_generator import generate_brief_file
from services.brief_editor import edit_brief_with_prompt

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload cap

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_FOLDER = os.path.join(_BASE_DIR, "generated")
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Only generated files produced by this app are allowed through download routes
_GENERATED_FILE_RE = re.compile(r"^brief_[a-f0-9]{32}\.(docx|pdf)$")

VALID_FORMATS = {"docx", "pdf"}


# ── Startup helpers ───────────────────────────────────────────────────────────

def _check_env():
    """Fail fast on startup if required Azure env vars are missing."""
    from services.ai_service import get_azure_client, _get_deployment
    get_azure_client()
    _get_deployment()


def _cleanup_generated_files():
    """Delete generated files older than 24 h to prevent disk accumulation."""
    cutoff = datetime.now() - timedelta(hours=24)
    try:
        for fname in os.listdir(GENERATED_FOLDER):
            path = os.path.join(GENERATED_FOLDER, fname)
            if os.path.isfile(path):
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if mtime < cutoff:
                    os.remove(path)
                    logger.info("Cleaned up old generated file: %s", fname)
    except OSError as exc:
        logger.warning("File cleanup error: %s", exc)


# ── Request helpers ───────────────────────────────────────────────────────────

def _json_error(msg, status=400):
    return Response(
        json.dumps({"error": msg}, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
        status=status,
    )


def _require_json(*keys):
    """Parse JSON body and check required keys. Returns (data, error_response)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _json_error("Request body must be a JSON object")
    for key in keys:
        if key not in data:
            return None, _json_error(f"Missing required field: '{key}'")
    return data, None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    tmp_paths = []
    try:
        raw_message = request.form.get("message", "").strip()
        uploaded_files = request.files.getlist("files")

        for file in uploaded_files:
            if not file or not file.filename:
                continue
            suffix = os.path.splitext(secure_filename(file.filename))[1]
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            file.save(tmp_path)
            tmp_paths.append(tmp_path)

        result = analyze_inputs(
            raw_texts=[raw_message] if raw_message else [],
            file_paths=tmp_paths,
        )

        return Response(
            json.dumps(result, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as exc:
        logger.exception("Error in /analyze")
        return _json_error(str(exc), 500)
    finally:
        for path in tmp_paths:
            try:
                os.remove(path)
            except OSError:
                pass


@app.route("/chat_answer", methods=["POST"])
def chat_answer():
    try:
        data, err = _require_json("brief", "field", "conversation_history")
        if err:
            return err

        brief = data["brief"]
        sources = data.get("sources", [])
        combined_text = data.get("combined_text", "")
        field = data["field"]
        conversation_history = data["conversation_history"]

        if not isinstance(brief, dict):
            return _json_error("'brief' must be an object")
        if not isinstance(conversation_history, list):
            return _json_error("'conversation_history' must be an array")

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
                if isinstance(raw_value, list):
                    brief[field] = [str(item).strip() for item in raw_value if str(item).strip()]
                else:
                    items = re.split(r"[,;\n]+", raw_value)
                    brief[field] = [item.strip() for item in items if item.strip()]
            else:
                brief[field] = raw_value.strip() if isinstance(raw_value, str) else str(raw_value)

            missing_fields = detect_missing_fields(brief)

            return Response(
                json.dumps({
                    "status": "accepted",
                    "response": result.get("response", ""),
                    "payload": {
                        "brief": brief,
                        "sources": sources,
                        "combined_text": combined_text,
                        "missing_fields": missing_fields,
                    },
                }, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
            )

        return Response(
            json.dumps({
                "status": status,
                "response": result.get("response", ""),
                "payload": {
                    "brief": brief,
                    "sources": sources,
                    "combined_text": combined_text,
                    "missing_fields": detect_missing_fields(brief),
                },
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as exc:
        logger.exception("Error in /chat_answer")
        return _json_error(str(exc), 500)


@app.route("/update_brief", methods=["POST"])
def update_brief():
    try:
        data, err = _require_json("brief", "field", "answer")
        if err:
            return err

        brief = data["brief"]
        field = data["field"]
        answer = data["answer"]

        if not isinstance(brief, dict):
            return _json_error("'brief' must be an object")
        if not isinstance(answer, str):
            return _json_error("'answer' must be a string")
        if len(answer) > 10_000:
            return _json_error("'answer' is too long (max 10 000 characters)")

        field_type = FIELD_RULES.get(field, {}).get("type", "string")

        if field_type == "list":
            items = re.split(r"[,;\n]+", answer)
            brief[field] = [item.strip() for item in items if item.strip()]
        else:
            brief[field] = answer.strip()

        missing_fields = detect_missing_fields(brief)

        return Response(
            json.dumps({"brief": brief, "missing_fields": missing_fields}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as exc:
        logger.exception("Error in /update_brief")
        return _json_error(str(exc), 500)


@app.route("/edit_brief", methods=["POST"])
def edit_brief():
    try:
        data, err = _require_json("brief", "prompt")
        if err:
            return err

        brief = data["brief"]
        edit_prompt = data["prompt"]

        if not isinstance(brief, dict):
            return _json_error("'brief' must be an object")
        if not isinstance(edit_prompt, str) or not edit_prompt.strip():
            return _json_error("'prompt' must be a non-empty string")

        result = edit_brief_with_prompt(brief, edit_prompt)

        updated_fields = result.get("updated_fields", {})
        for field, value in updated_fields.items():
            field_type = FIELD_RULES.get(field, {}).get("type", "string")
            if field_type == "list":
                if isinstance(value, list):
                    brief[field] = [str(v).strip() for v in value if str(v).strip()]
                else:
                    items = re.split(r"[,;\n]+", str(value))
                    brief[field] = [item.strip() for item in items if item.strip()]
            else:
                brief[field] = str(value).strip() if value else ""

        missing_fields = detect_missing_fields(brief)

        return Response(
            json.dumps({
                "brief": brief,
                "missing_fields": missing_fields,
                "updated_fields": list(updated_fields.keys()),
                "response": result.get("response", ""),
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as exc:
        logger.exception("Error in /edit_brief")
        return _json_error(str(exc), 500)


@app.route("/finalize", methods=["POST"])
def finalize():
    try:
        data, err = _require_json("brief")
        if err:
            return err

        brief = data["brief"]
        sources = data.get("sources", [])
        combined_text = data.get("combined_text", "")
        file_format = str(data.get("format", "docx")).strip().lower()

        if not isinstance(brief, dict):
            return _json_error("'brief' must be an object")
        if file_format not in VALID_FORMATS:
            return _json_error(f"Invalid format '{file_format}'. Use 'docx' or 'pdf'")

        missing_fields = detect_missing_fields(brief)
        if missing_fields:
            return Response(
                json.dumps({
                    "error": "Brief nadal ma brakujące pola",
                    "missing_fields": missing_fields,
                }, ensure_ascii=False),
                mimetype="application/json; charset=utf-8",
                status=400,
            )

        document_brief = build_document_brief(
            brief=brief,
            sources=sources,
            combined_text=combined_text,
        )

        file_path = generate_brief_file(
            brief=document_brief,
            file_format=file_format,
            output_dir=GENERATED_FOLDER,
        )

        filename = os.path.basename(file_path)
        logger.info("Generated %s file: %s", file_format.upper(), filename)

        return Response(
            json.dumps({
                "message": "Document brief i plik zostały wygenerowane",
                "document_brief": document_brief,
                "file_path": file_path,
                "download_url": f"/download-generated/{filename}",
                "format": file_format,
            }, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    except Exception as exc:
        logger.exception("Error in /finalize")
        return _json_error(str(exc), 500)


@app.route("/download-generated/<filename>", methods=["GET"])
def download_generated(filename):
    if not _GENERATED_FILE_RE.match(filename):
        return _json_error("Not found", 404)
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)


@app.route("/preview-generated/<filename>", methods=["GET"])
def preview_generated(filename):
    if not _GENERATED_FILE_RE.match(filename):
        return _json_error("Not found", 404)
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=False)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _check_env()
    _cleanup_generated_files()
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
