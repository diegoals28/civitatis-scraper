"""
Scheduled scraping job for Civitatis
Runs daily at 6:00 AM to scrape all tours for the next 30 days
"""

import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from models import db, Tour, Schedule, ScrapeLog
from scraper import compare_all_schedules

# Default tours to scrape
DEFAULT_TOURS = [
    {
        "name": "Coliseo, Foro y Palatino",
        "url": "https://www.civitatis.com/es/roma/visita-guiada-roma-antigua/"
    },
    {
        "name": "Museos Vaticanos y Capilla Sixtina",
        "url": "https://www.civitatis.com/es/roma/visita-guiada-vaticano/"
    },
    {
        "name": "Coliseo + Arena de Gladiadores",
        "url": "https://www.civitatis.com/es/roma/tour-coliseo-arena-gladiadores/"
    }
]

scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Rome'))


def init_scheduler(app):
    """Initialize the scheduler with the Flask app context"""
    # Automatic daily scrape disabled - user prefers manual scraping of selected dates
    # The scheduler is kept but no jobs are added
    # scheduler.start()
    print("Scheduler initialized (automatic scrape disabled - use manual selection)", flush=True)


def ensure_tours_exist():
    """Ensure default tours exist in database"""
    for tour_data in DEFAULT_TOURS:
        tour = Tour.query.filter_by(url=tour_data['url']).first()
        if not tour:
            tour = Tour(name=tour_data['name'], url=tour_data['url'])
            db.session.add(tour)
    db.session.commit()


def run_daily_scrape():
    """Run the daily scrape for all tours, next 30 days"""
    import sys
    print(f"=== SCRAPE STARTED at {datetime.now()} ===", flush=True)
    sys.stdout.flush()

    # Create log entry
    log = ScrapeLog(status='running')
    db.session.add(log)
    db.session.commit()
    print(f"Log created with id {log.id}", flush=True)

    try:
        ensure_tours_exist()
        tours = Tour.query.all()
        print(f"Found {len(tours)} tours to scrape", flush=True)

        # Generate dates for next 30 days
        today = datetime.now().date()
        dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]

        total_tours = 0
        total_dates = 0

        for tour in tours:
            print(f"Scraping tour: {tour.name}", flush=True)

            for idx, date_str in enumerate(dates):
                try:
                    print(f"  [{idx+1}/30] {date_str}...", end=" ", flush=True)
                    # Run scraper
                    results = asyncio.run(compare_all_schedules(tour.url, date_str))
                    print(f"OK ({len(results)} schedules)", flush=True)

                    # Delete old data for this tour/date
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    Schedule.query.filter_by(tour_id=tour.id, date=date_obj).delete()

                    # Save new data
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

                    db.session.commit()
                    total_dates += 1

                except Exception as e:
                    print(f"Error scraping {tour.name} for {date_str}: {e}", flush=True)
                    db.session.rollback()

            total_tours += 1

        # Update log
        log.finished_at = datetime.utcnow()
        log.status = 'success'
        log.tours_scraped = total_tours
        log.dates_scraped = total_dates
        db.session.commit()

        print(f"Daily scrape completed: {total_tours} tours, {total_dates} dates", flush=True)

    except Exception as e:
        log.finished_at = datetime.utcnow()
        log.status = 'failed'
        log.error_message = str(e)
        db.session.commit()
        print(f"Daily scrape failed: {e}", flush=True)


def run_scrape_now(app):
    """Manually trigger a scrape (for testing or manual refresh)"""
    with app.app_context():
        run_daily_scrape()
