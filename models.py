"""
Database models for Civitatis scraper
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Tour(db.Model):
    """Tour definition"""
    __tablename__ = 'tours'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    schedules = db.relationship('Schedule', backref='tour', lazy=True, cascade='all, delete-orphan')


class Schedule(db.Model):
    """Scraped schedule data"""
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    tour_id = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10), nullable=False)
    operator = db.Column(db.String(100))
    provider_id = db.Column(db.String(20))
    price = db.Column(db.String(20))
    quota = db.Column(db.String(50))
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_tour_date', 'tour_id', 'date'),
    )


class ScrapeLog(db.Model):
    """Log of scrape runs"""
    __tablename__ = 'scrape_logs'

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(20))  # running, success, failed
    tours_scraped = db.Column(db.Integer, default=0)
    dates_scraped = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
