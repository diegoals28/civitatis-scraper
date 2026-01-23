"""
Civitatis Tour Operator Scraper - Flask Backend
"""

import os
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from models import db, Tour, Schedule, ScrapeLog
from scraper import compare_all_schedules

app = Flask(__name__)
CORS(app)

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Fix for Railway PostgreSQL URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
else:
    # Use SQLite as fallback
    database_url = 'sqlite:///civitatis.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Initialize database and scheduler
try:
    with app.app_context():
        db.create_all()
        print(f"Database connected: {database_url[:30]}...", flush=True)

        # Import and start scheduler
        from scheduler import init_scheduler, ensure_tours_exist
        ensure_tours_exist()
        init_scheduler(app)
except Exception as e:
    print(f"Database initialization error: {e}", flush=True)
    print("App will start but database features won't work until DATABASE_URL is configured", flush=True)


@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/scrape", methods=["POST"])
def scrape():
    """
    API endpoint to scrape tour operator information (real-time).
    Also saves results to database.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No se recibieron datos JSON"}), 400

        url = data.get("url")
        date = data.get("date")
        language = data.get("language", "es")

        if not url:
            return jsonify({"success": False, "error": "La URL del tour es requerida"}), 400

        if not date:
            return jsonify({"success": False, "error": "La fecha es requerida"}), 400

        if "civitatis.com" not in url:
            return jsonify({"success": False, "error": "La URL debe ser de civitatis.com"}), 400

        results = asyncio.run(compare_all_schedules(url, date, language))

        # Save results to database
        tour = Tour.query.filter_by(url=url).first()
        if tour and results:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            # Delete old data for this tour/date
            deleted = Schedule.query.filter_by(tour_id=tour.id, date=date_obj).delete()
            print(f"Deleted {deleted} old schedules for {date}", flush=True)

            # Save new data
            saved_count = 0
            for result in results:
                if result.get('time') and result['time'] != 'N/A':
                    schedule = Schedule(
                        tour_id=tour.id,
                        date=date_obj,
                        time=result['time'],
                        operator=result.get('operator'),
                        provider_id=result.get('provider_id'),
                        price=result.get('price'),
                        quota=result.get('quota')
                    )
                    db.session.add(schedule)
                    saved_count += 1

            db.session.commit()
            print(f"Saved {saved_count} schedules for {date}", flush=True)
        else:
            print(f"Tour not found for URL: {url}" if not tour else f"No results for {date}", flush=True)

        return jsonify({"success": True, "data": results})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Error durante el scraping: {str(e)}"}), 500


@app.route("/api/tours", methods=["GET"])
def get_tours():
    """Get list of configured tours"""
    tours = Tour.query.all()
    return jsonify({
        "success": True,
        "data": [{"id": t.id, "name": t.name, "url": t.url} for t in tours]
    })


@app.route("/api/schedules/<int:tour_id>", methods=["GET"])
def get_schedules(tour_id):
    """Get stored schedules for a tour"""
    tour = Tour.query.get_or_404(tour_id)

    # Get date range from query params or default to next 30 days
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date:
        start_date = datetime.now().date()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    if not end_date:
        end_date = start_date + timedelta(days=30)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    schedules = Schedule.query.filter(
        Schedule.tour_id == tour_id,
        Schedule.date >= start_date,
        Schedule.date <= end_date
    ).order_by(Schedule.date, Schedule.time).all()

    # Group by date
    grouped = {}
    for s in schedules:
        date_str = s.date.strftime('%Y-%m-%d')
        if date_str not in grouped:
            grouped[date_str] = []
        grouped[date_str].append({
            "time": s.time,
            "operator": s.operator,
            "price": s.price,
            "quota": s.quota,
            "provider_id": s.provider_id
        })

    return jsonify({
        "success": True,
        "tour": {"id": tour.id, "name": tour.name},
        "data": grouped
    })


@app.route("/api/schedules/date/<date_str>", methods=["GET"])
def get_schedules_by_date(date_str):
    """Get schedules for all tours on a specific date"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"success": False, "error": "Formato de fecha invalido"}), 400

    tour_id = request.args.get('tour_id')

    query = Schedule.query.filter(Schedule.date == date_obj)
    if tour_id:
        query = query.filter(Schedule.tour_id == int(tour_id))

    schedules = query.order_by(Schedule.time).all()

    result = []
    for s in schedules:
        result.append({
            "time": s.time,
            "operator": s.operator,
            "price": s.price,
            "quota": s.quota,
            "tour_id": s.tour_id,
            "tour_name": s.tour.name
        })

    return jsonify({
        "success": True,
        "date": date_str,
        "data": result
    })


@app.route("/api/calendar/<int:tour_id>", methods=["GET"])
def get_calendar_data(tour_id):
    """Get calendar data with availability summary for each date"""
    tour = Tour.query.get_or_404(tour_id)

    # Get schedules for next 30 days
    today = datetime.now().date()
    end_date = today + timedelta(days=30)

    schedules = Schedule.query.filter(
        Schedule.tour_id == tour_id,
        Schedule.date >= today,
        Schedule.date <= end_date
    ).all()

    # Group by date with summary
    calendar_data = {}
    for s in schedules:
        date_str = s.date.strftime('%Y-%m-%d')
        if date_str not in calendar_data:
            calendar_data[date_str] = {
                "schedules": [],
                "has_data": True
            }
        calendar_data[date_str]["schedules"].append({
            "time": s.time,
            "operator": s.operator,
            "price": s.price,
            "quota": s.quota
        })

    return jsonify({
        "success": True,
        "tour": {"id": tour.id, "name": tour.name},
        "calendar": calendar_data
    })


@app.route("/api/scrape/manual", methods=["POST"])
def manual_scrape():
    """Trigger a manual scrape (admin only - consider adding auth)"""
    from scheduler import run_scrape_now
    import threading

    # Run in background thread to not block response
    thread = threading.Thread(target=run_scrape_now, args=(app,))
    thread.start()

    return jsonify({
        "success": True,
        "message": "Scrape started in background"
    })


@app.route("/api/scrape/status", methods=["GET"])
def scrape_status():
    """Get latest scrape log status"""
    log = ScrapeLog.query.order_by(ScrapeLog.id.desc()).first()

    if not log:
        return jsonify({
            "success": True,
            "last_scrape": None
        })

    # Auto-fix stuck scrapes (running for more than 30 minutes)
    if log.status == 'running' and log.started_at:
        elapsed = datetime.utcnow() - log.started_at
        if elapsed.total_seconds() > 1800:  # 30 minutes
            log.status = 'failed'
            log.finished_at = datetime.utcnow()
            log.error_message = 'Scrape timeout - took longer than 30 minutes'
            db.session.commit()

    return jsonify({
        "success": True,
        "last_scrape": {
            "started_at": (log.started_at.isoformat() + "Z") if log.started_at else None,
            "finished_at": (log.finished_at.isoformat() + "Z") if log.finished_at else None,
            "status": log.status,
            "tours_scraped": log.tours_scraped,
            "dates_scraped": log.dates_scraped,
            "error": log.error_message
        }
    })


@app.route("/api/scrape/reset", methods=["POST"])
def reset_scrape_status():
    """Reset stuck scrape status"""
    log = ScrapeLog.query.order_by(ScrapeLog.id.desc()).first()

    if log and log.status == 'running':
        log.status = 'failed'
        log.finished_at = datetime.utcnow()
        log.error_message = 'Manually reset'
        db.session.commit()
        return jsonify({"success": True, "message": "Scrape status reset"})

    return jsonify({"success": True, "message": "No running scrape to reset"})


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask on port {port}...", flush=True)
    app.run(debug=False, host="0.0.0.0", port=port)
