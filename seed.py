"""Seed demo data: villages/areas + historical + recent reports.

One area ('Kondapalli') is seeded with a deliberate spike in the last few
days so the outbreak-detection algorithm has something real to flag when
you first open the dashboard.
"""
import random
from datetime import date, timedelta

AREAS = [
    # name, pincode, lat, lng, population
    ("Kondapalli", "521228", 16.6167, 80.5167, 18000),
    ("Mangalagiri", "522503", 16.4307, 80.5525, 45000),
    ("Tadepalli", "522501", 16.4930, 80.6060, 32000),
    ("Guntur Rural", "522001", 16.3067, 80.4365, 51000),
    ("Vijayawada North", "520001", 16.5193, 80.6305, 62000),
    ("Nuzvid", "521201", 16.7900, 80.8450, 27000),
    ("Sattenapalle", "522403", 16.3960, 80.1490, 21000),
    ("Amaravati", "522020", 16.5130, 80.5180, 15000),
]

WATER_SOURCES = ["Borewell", "Public tap", "Open well", "Pond / lake", "Water tanker", "Packaged / bottled", "River", "Other"]
SYMPTOM_KEYS = ["diarrhea", "vomiting", "fever", "stomach_cramps", "dehydration", "nausea", "jaundice", "bloody_stool"]
SEVERITIES = ["Mild", "Moderate", "Severe"]
REPORTER_TYPES = ["Self", "Health Worker"]


def _rand_symptoms():
    n = random.choice([1, 2, 2, 3])
    return random.sample(SYMPTOM_KEYS, n)


def run_seed(db):
    from app import Area, Report

    area_objs = {}
    for name, pincode, lat, lng, pop in AREAS:
        a = Area(name=name, pincode=pincode, lat=lat, lng=lng, population=pop)
        db.session.add(a)
        area_objs[name] = a
    db.session.commit()

    today = date.today()

    # --- Baseline "normal" noise for every area over the last 30 days ---
    for name, area in area_objs.items():
        baseline_daily_avg = random.uniform(0.05, 0.35)
        for days_ago in range(30, 0, -1):
            d = today - timedelta(days=days_ago)
            if random.random() < baseline_daily_avg:
                _add_report(db, area, d)

    # --- Deliberate outbreak cluster in Kondapalli over the last 5 days ---
    outbreak_area = area_objs["Kondapalli"]
    for days_ago in range(5, -1, -1):
        d = today - timedelta(days=days_ago)
        n_reports = random.randint(2, 4) + (2 if days_ago <= 2 else 0)
        for _ in range(n_reports):
            _add_report(
                db, outbreak_area, d,
                forced_source="Open well",
                forced_symptoms=["diarrhea", "vomiting", "dehydration"],
                forced_severity=random.choice(["Moderate", "Severe"]),
            )

    # --- Mild watch-level bump in Tadepalli in the last few days ---
    watch_area = area_objs["Tadepalli"]
    for days_ago in range(4, -1, -1):
        d = today - timedelta(days=days_ago)
        if random.random() < 0.6:
            _add_report(db, watch_area, d, forced_source="Water tanker")

    db.session.commit()


def _add_report(db, area, onset_date, forced_source=None, forced_symptoms=None, forced_severity=None):
    from app import Report
    r = Report(
        area_id=area.id,
        reporter_name=None,
        reporter_type=random.choice(REPORTER_TYPES),
        age=random.randint(2, 75),
        symptoms=",".join(forced_symptoms or _rand_symptoms()),
        water_source=forced_source or random.choice(WATER_SOURCES),
        severity=forced_severity or random.choice(SEVERITIES),
        onset_date=onset_date,
        notes=None,
    )
    db.session.add(r)
