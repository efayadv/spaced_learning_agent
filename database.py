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
            """)
    finally:
        connection.close()