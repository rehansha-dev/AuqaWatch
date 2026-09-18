"""
Community Water-Borne Illness & Outbreak Early Warning System
Track 2: Social Impact

A Flask web application that lets community members / health workers report
water-borne illness symptoms, and gives public-health admins a real-time
dashboard with an outbreak-detection algorithm (rolling window + baseline
comparison) to flag emerging clusters early.
"""

import os
import json
import math
from datetime import datetime, timedelta, date
from collections import defaultdict

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "outbreak.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# Config: outbreak detection tuning
# ---------------------------------------------------------------------------
ROLLING_WINDOW_DAYS = 7          # window used to detect an active cluster
BASELINE_WINDOW_DAYS = 30        # history used to compute "normal" for an area
WATCH_MULTIPLIER = 1.8           # window count > baseline*this => WATCH
ALERT_MULTIPLIER = 3.0           # window count > baseline*this => ALERT
COLD_START_WATCH = 3             # absolute fallback thresholds when no baseline yet
COLD_START_ALERT = 6

SYMPTOM_LIST = [
    ("diarrhea", "Diarrhea", 3),
    ("vomiting", "Vomiting", 3),
    ("fever", "Fever", 2),
    ("stomach_cramps", "Stomach cramps", 2),
    ("dehydration", "Dehydration", 4),
    ("nausea", "Nausea", 1),
    ("jaundice", "Jaundice (yellow skin/eyes)", 5),
    ("bloody_stool", "Blood in stool", 5),
]
SYMPTOM_WEIGHTS = {key: weight for key, _, weight in SYMPTOM_LIST}

WATER_SOURCES = ["Borewell", "Public tap", "Open well", "Pond / lake", "Water tanker", "Packaged / bottled", "River", "Other"]

SEVERITY_LEVELS = ["Mild", "Moderate", "Severe"]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # demo only — change before real deployment


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Area(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    pincode = db.Column(db.String(10))
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    population = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "pincode": self.pincode,
            "lat": self.lat, "lng": self.lng, "population": self.population,
        }


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)
    reporter_name = db.Column(db.String(120))
    reporter_type = db.Column(db.String(30), default="Self")  # Self / Health Worker
    age = db.Column(db.Integer)
    symptoms = db.Column(db.String(300), default="")  # comma-separated keys
    water_source = db.Column(db.String(60))
    severity = db.Column(db.String(20), default="Mild")
    onset_date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    area = db.relationship("Area", backref="reports")

    @property
    def symptom_list(self):
        return [s for s in self.symptoms.split(",") if s]

    @property
    def symptom_score(self):
        return sum(SYMPTOM_WEIGHTS.get(s, 1) for s in self.symptom_list)

    def to_dict(self):
        return {
            "id": self.id,
            "area": self.area.name if self.area else "Unknown",
            "area_id": self.area_id,
            "lat": self.area.lat if self.area else None,
            "lng": self.area.lng if self.area else None,
            "reporter_type": self.reporter_type,
            "age": self.age,
            "symptoms": self.symptom_list,
            "water_source": self.water_source,
            "severity": self.severity,
            "onset_date": self.onset_date.isoformat() if self.onset_date else None,
            "created_at": self.created_at.isoformat(),
            "symptom_score": self.symptom_score,
        }


# ---------------------------------------------------------------------------
# Outbreak detection
# ---------------------------------------------------------------------------
def compute_area_status(area, today=None):
    """Return risk status for a single area using rolling-window vs baseline."""
    today = today or date.today()
    window_start = today - timedelta(days=ROLLING_WINDOW_DAYS)
    baseline_start = today - timedelta(days=BASELINE_WINDOW_DAYS)

    window_reports = [r for r in area.reports if r.onset_date and window_start <= r.onset_date <= today]
    baseline_reports = [r for r in area.reports if r.onset_date and baseline_start <= r.onset_date < window_start]

    window_count = len(window_reports)
    baseline_days = max(1, (window_start - baseline_start).days)
    baseline_daily_rate = len(baseline_reports) / baseline_days
    expected_in_window = baseline_daily_rate * ROLLING_WINDOW_DAYS

    has_baseline = len(baseline_reports) >= 3

    if has_baseline:
        watch_th = max(expected_in_window * WATCH_MULTIPLIER, COLD_START_WATCH)
        alert_th = max(expected_in_window * ALERT_MULTIPLIER, COLD_START_ALERT)
    else:
        watch_th = COLD_START_WATCH
        alert_th = COLD_START_ALERT

    if window_count >= alert_th and window_count >= 3:
        status = "alert"
    elif window_count >= watch_th and window_count >= 2:
        status = "watch"
    else:
        status = "normal"

    avg_severity_score = (
        sum(r.symptom_score for r in window_reports) / window_count if window_count else 0
    )

    # simple trend: compare first half vs second half of window
    mid = today - timedelta(days=ROLLING_WINDOW_DAYS // 2)
    recent_half = len([r for r in window_reports if r.onset_date >= mid])
    older_half = window_count - recent_half
    if older_half == 0 and recent_half > 0:
        trend = "rising"
    elif recent_half > older_half:
        trend = "rising"
    elif recent_half < older_half:
        trend = "falling"
    else:
        trend = "steady"

    dominant_source = None
    if window_reports:
        counts = defaultdict(int)
        for r in window_reports:
            counts[r.water_source or "Unknown"] += 1
        dominant_source = max(counts.items(), key=lambda kv: kv[1])[0]

    return {
        "area": area.to_dict(),
        "window_count": window_count,
        "expected": round(expected_in_window, 1),
        "status": status,
        "trend": trend,
        "avg_severity_score": round(avg_severity_score, 1),
        "dominant_water_source": dominant_source,
        "has_baseline": has_baseline,
    }


def all_area_statuses():
    areas = Area.query.all()
    return [compute_area_status(a) for a in areas]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def is_logged_in():
    return session.get("is_admin", False)


@app.context_processor
def inject_globals():
    return {"is_logged_in": is_logged_in()}


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    areas = Area.query.order_by(Area.name).all()
    return render_template(
        "index.html", areas=areas, symptoms=SYMPTOM_LIST,
        water_sources=WATER_SOURCES, severities=SEVERITY_LEVELS,
        today=date.today().isoformat(),
    )


@app.route("/report", methods=["POST"])
def submit_report():
    form = request.form
    area_id = form.get("area_id")
    if not area_id:
        flash("Please choose your area/village.", "error")
        return redirect(url_for("index"))

    symptoms_selected = form.getlist("symptoms")
    onset_str = form.get("onset_date") or date.today().isoformat()
    try:
        onset = datetime.strptime(onset_str, "%Y-%m-%d").date()
    except ValueError:
        onset = date.today()

    report = Report(
        area_id=int(area_id),
        reporter_name=form.get("reporter_name") or None,
        reporter_type=form.get("reporter_type") or "Self",
        age=int(form["age"]) if form.get("age") else None,
        symptoms=",".join(symptoms_selected),
        water_source=form.get("water_source"),
        severity=form.get("severity") or "Mild",
        onset_date=onset,
        notes=form.get("notes") or None,
    )
    db.session.add(report)
    db.session.commit()
    return redirect(url_for("report_success"))


@app.route("/report/success")
def report_success():
    return render_template("report_success.html")


# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Dashboard (admin)
# ---------------------------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ---------------------------------------------------------------------------
# JSON APIs used by the dashboard
# ---------------------------------------------------------------------------
@app.route("/api/summary")
def api_summary():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401

    statuses = all_area_statuses()
    total_reports = Report.query.count()
    today_count = Report.query.filter(Report.onset_date == date.today()).count()
    alerts = [s for s in statuses if s["status"] == "alert"]
    watches = [s for s in statuses if s["status"] == "watch"]

    return jsonify({
        "total_reports": total_reports,
        "today_reports": today_count,
        "areas_monitored": len(statuses),
        "active_alerts": len(alerts),
        "active_watches": len(watches),
        "statuses": sorted(statuses, key=lambda s: (-{"alert": 2, "watch": 1, "normal": 0}[s["status"]], -s["window_count"])),
    })


@app.route("/api/timeseries")
def api_timeseries():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401
    days = int(request.args.get("days", 14))
    today = date.today()
    counts = defaultdict(int)
    start = today - timedelta(days=days - 1)
    for r in Report.query.filter(Report.onset_date >= start).all():
        counts[r.onset_date.isoformat()] += 1
    labels = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    values = [counts.get(d, 0) for d in labels]
    return jsonify({"labels": labels, "values": values})


@app.route("/api/symptom-distribution")
def api_symptom_distribution():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401
    counts = defaultdict(int)
    for r in Report.query.all():
        for s in r.symptom_list:
            counts[s] += 1
    label_map = {key: label for key, label, _ in SYMPTOM_LIST}
    labels = [label_map.get(k, k) for k in counts.keys()]
    values = list(counts.values())
    return jsonify({"labels": labels, "values": values})


@app.route("/api/reports")
def api_reports():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401
    q = Report.query.order_by(Report.created_at.desc())
    area_filter = request.args.get("area_id")
    if area_filter:
        q = q.filter(Report.area_id == int(area_filter))
    reports = q.limit(300).all()
    return jsonify([r.to_dict() for r in reports])


@app.route("/api/water-source-breakdown")
def api_water_source_breakdown():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401
    counts = defaultdict(int)
    for r in Report.query.all():
        counts[r.water_source or "Unknown"] += 1
    return jsonify({"labels": list(counts.keys()), "values": list(counts.values())})


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")


@app.cli.command("seed")
def seed_cmd():
    from seed import run_seed
    run_seed(db)
    print("Seed data inserted.")


def ensure_db():
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    with app.app_context():
        db.create_all()
        if Area.query.count() == 0:
            from seed import run_seed
            run_seed(db)


if __name__ == "__main__":
    ensure_db()
    app.run(debug=True, port=5000)
