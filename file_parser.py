import json
import logging
import os
from datetime import datetime
from pypdf import PdfReader
import docx
import pptx
from openpyxl import load_workbook
from email import policy
from email.parser import BytesParser

logger = logging.getLogger(__name__)


class BriefInputParser:
    def _extract_pdf(self, file_path):
        text = ""
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            return f"[PDF READ ERROR: {e}]"
        return text.strip()

    def _extract_docx(self, file_path):
        text = ""
        try:
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n"
        except Exception as e:
            return f"[DOCX READ ERROR: {e}]"
        return text.strip()

    def _extract_pptx(self, file_path):
        text = ""
        try:
            prs = pptx.Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        text += shape.text + "\n"
        except Exception as e:
            return f"[PPTX READ ERROR: {e}]"
        return text.strip()

    def _extract_eml(self, file_path):
        try:
            with open(file_path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)

            subject = msg.get("subject", "")
            sender = msg.get("from", "")
            to = msg.get("to", "")

            body_parts = []

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    disposition = str(part.get("Content-Disposition", ""))

                    if "attachment" in disposition.lower():
                        continue

                    if content_type == "text/plain":
                        try:
                            body_parts.append(part.get_content())
                        except Exception:
                            pass
            else:
                try:
                    body_parts.append(msg.get_content())
                except Exception:
                    pass

            body = "\n".join([p for p in body_parts if p])

            return f"From: {sender}\nTo: {to}\nSubject: {subject}\n\n{body}".strip()
        except Exception as e:
            return f"[EML READ ERROR: {e}]"

    def _extract_xlsx(self, file_path):
        text = ""
        try:
            wb = load_workbook(file_path, data_only=True)

            for sheet in wb.worksheets:
                text += f"\n--- SHEET: {sheet.title} ---\n"
                for row in sheet.iter_rows(values_only=True):
                    values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if values:
                        text += " | ".join(values) + "\n"

        except Exception as e:
            return f"[XLSX READ ERROR: {e}]"

        return text.strip()

    def generate_json_payload(self, raw_texts=None, file_paths=None, save_to_file=True):
        if raw_texts is None:
            raw_texts = []
        if file_paths is None:
            file_paths = []

        sources = []
        combined_text_list = []

        for text in raw_texts:
            if any(k in text for k in ["Od:", "From:", "Temat:", "Subject:"]):
                source_type = "email"
            else:
                source_type = "manual_text"

            sources.append({
                "type": source_type,
                "filename": None,
                "content": text
            })
            combined_text_list.append(f"--- SOURCE: {source_type.upper()} ---\n{text}")

        for file_path in file_paths:
            if not os.path.exists(file_path):
                logger.warning("File '%s' does not exist and will be skipped.", file_path)
                continue

            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            content = ""

            if ext == "pdf":
                content = self._extract_pdf(file_path)
                doc_type = "pdf"
            elif ext in ["docx", "doc"]:
                content = self._extract_docx(file_path)
                doc_type = "docx"
            elif ext == "pptx":
                content = self._extract_pptx(file_path)
                doc_type = "pptx"
            elif ext == "eml":
                content = self._extract_eml(file_path)
                doc_type = "email_file"
            elif ext == "xlsx":
                content = self._extract_xlsx(file_path)
                doc_type = "xlsx"
            else:
                content = f"[UNSUPPORTED FILE FORMAT: {ext}]"
                doc_type = "unknown"

            sources.append({
                "type": doc_type,
                "filename": filename,
                "content": content
            })
            combined_text_list.append(f"--- SOURCE: FILE {filename} ---\n{content}")

        result = {
            "sources": sources,
            "combined_text": "\n\n".join(combined_text_list)
        }

        json_string = json.dumps(result, ensure_ascii=False, indent=2)

        if save_to_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"parsed_input_{timestamp}.json"
            try:
                with open(output_filename, "w", encoding="utf-8") as f:
                    f.write(json_string)
                logger.info("Saved JSON file: %s", output_filename)
            except Exception as e:
                logger.warning("Save error: %s", e)

        return json_string