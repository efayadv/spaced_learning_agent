import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "teacher.db"

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def initialize_database():
    connection = get_connection()

    try:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS review_items (
                    id INTEGER PRIMARY KEY,
                    topic_id INTEGER NOT NULL,
                    learning_objective TEXT NOT NULL,
                    fsrs_card_json TEXT NOT NULL,
                    next_due_at TEXT NOT NULL,
                    FOREIGN KEY (topic_id) REFERENCES topics(id)
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY,
                    review_item_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    fsrs_review_log_json TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (review_item_id)
                        REFERENCES review_items(id)
                );

                CREATE INDEX IF NOT EXISTS idx_review_items_due
                ON review_items(next_due_at);

                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INTEGER PRIMARY KEY,
                    topic_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    notes TEXT,
                    assessment_status TEXT NOT NULL DEFAULT 'pending',
                    FOREIGN KEY (topic_id) REFERENCES topics(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_active_study_session
                ON study_sessions ((1))
                WHERE ended_at IS NULL;

                CREATE TABLE IF NOT EXISTS session_review_items (
                    session_id INTEGER NOT NULL,
                    review_item_id INTEGER NOT NULL,
                    PRIMARY KEY (session_id, review_item_id),
                    FOREIGN KEY (session_id) REFERENCES study_sessions(id),
                    FOREIGN KEY (review_item_id) REFERENCES review_items(id)
                );

                CREATE TABLE IF NOT EXISTS reminder_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 0,
                    daily_time TEXT NOT NULL DEFAULT '12:00',
                    followup_enabled INTEGER NOT NULL DEFAULT 1,
                    followup_time TEXT NOT NULL DEFAULT '19:00',
                    timezone TEXT NOT NULL DEFAULT 'America/Chicago'
                );

                INSERT OR IGNORE INTO reminder_settings (id) VALUES (1);

                CREATE TABLE IF NOT EXISTS reminder_deliveries (
                    local_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (local_date, slot)
                );
            """)
    finally:
        connection.close()