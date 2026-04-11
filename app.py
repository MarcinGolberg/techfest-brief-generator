from flask import Flask, request, jsonify, render_template
from services.brief_pipeline import analyze_inputs

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    raw_texts = data.get("raw_texts", [])
    file_paths = data.get("file_paths", [])

    try:
        result = analyze_inputs(raw_texts=raw_texts, file_paths=file_paths)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)