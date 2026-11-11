import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
DB_PATH = os.path.join(DATA_DIR, "reunite.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS camps (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    district TEXT NOT NULL,
    lat REAL, lng REAL,
    capacity INTEGER
);
-- People registered at a camp at the moment of intake.
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    ref TEXT UNIQUE NOT NULL,
    name TEXT,
    age INTEGER,
    gender TEXT,
    origin TEXT,
    marks TEXT,
    camp_id INTEGER NOT NULL REFERENCES camps(id),
    tent TEXT,
    photo TEXT,
    embedding BLOB,
    status TEXT NOT NULL DEFAULT 'registered',   -- registered | reunited
    consent INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Searches filed by families. Kept open so later arrivals are matched at intake.
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    ref TEXT UNIQUE NOT NULL,
    seeker_name TEXT,
    seeker_phone TEXT,
    relation TEXT,
    name TEXT,
    age INTEGER,
    gender TEXT,
    last_seen TEXT,
    marks TEXT,
    photo TEXT,
    embedding BLOB,
    status TEXT NOT NULL DEFAULT 'open',          -- open | resolved
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Candidate matches. AI suggests, a volunteer confirms.
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    person_id INTEGER NOT NULL REFERENCES people(id),
    confidence REAL NOT NULL,
    face_score REAL,
    text_score REAL,
    method TEXT NOT NULL,                         -- face | text | face+text
    status TEXT NOT NULL DEFAULT 'pending',       -- pending | verified | rejected
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(report_id, person_id)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    camp_id INTEGER,
    match_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(PHOTO_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
