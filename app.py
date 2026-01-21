"""
Civitatis Tour Operator Scraper - Flask Backend
"""
print("=== APP.PY STARTING ===", flush=True)

import asyncio
print("asyncio imported", flush=True)
from flask import Flask, render_template, request, jsonify
print("flask imported", flush=True)
from flask_cors import CORS
print("flask_cors imported", flush=True)
from scraper import compare_all_schedules
print("scraper imported", flush=True)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes


@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/scrape", methods=["POST"])
def scrape():
    """
    API endpoint to scrape tour operator information.

    Expected JSON body:
    {
        "url": "https://www.civitatis.com/...",
        "date": "YYYY-MM-DD",
        "language": "es"  // optional, defaults to "es"
    }

    Returns:
    {
        "success": true/false,
        "data": [
            {"time": "09:00", "operator": "Operator Name", "price": "25.00"},
            ...
        ],
        "error": "error message if success is false"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "No se recibieron datos JSON"
            }), 400

        url = data.get("url")
        date = data.get("date")
        language = data.get("language", "es")

        if not url:
            return jsonify({
                "success": False,
                "error": "La URL del tour es requerida"
            }), 400

        if not date:
            return jsonify({
                "success": False,
                "error": "La fecha es requerida"
            }), 400

        # Validate URL is from civitatis
        if "civitatis.com" not in url:
            return jsonify({
                "success": False,
                "error": "La URL debe ser de civitatis.com"
            }), 400

        # Run the async scraper
        results = asyncio.run(compare_all_schedules(url, date, language))

        return jsonify({
            "success": True,
            "data": results
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error durante el scraping: {str(e)}"
        }), 500


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask on port {port}...", flush=True)
    app.run(debug=False, host="0.0.0.0", port=port)
