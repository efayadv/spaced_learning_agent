from datetime import datetime, timezone

from fsrs import Card

from database import get_connection

def add_review_item(topic_name: str, learning_objective: str):
    topic_name = topic_name.strip()
    learning_objective = learning_objective.strip()

    if not topic_name or not learning_objective:
        raise ValueError("Topic and learning objective cannot be empty.")

    card = Card()
    connection = get_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO topics (name) VALUES (?)", 
                    (topic_name,),
                )
            topic = connection.execute(
                "SELECT id FROM topics WHERE name = ?",
                    (topic_name,),
            ).fetchone()

            cursor = connection.execute("""
                INSERT INTO review_items (
                    topic_id,
                    learning_objective,
                    fsrs_card_json,
                    next_due_at
                ) VALUES (?, ?, ?, ?)
            """,
                (
                    topic["id"],
                    learning_objective,
                    card.to_json,
                    card.due.isoformat(),  
                ),
            )

            return cursor.lastrowid
        
    finally:
        connection.close()

def get_due_items():
    now = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT 
                review_items.id,
                topics.name AS topic,
                review_items.learning_objective
                review_items.next_due_at
            FROM review_items
            JOIN topics ON topics.id = review_items.id
            WHERE review_items.next_due_at <= ?
            ORDER BY review_items.next_due_at
            """,
            (now,),
        ).fetchall()

        return [dict(row) for row in rows]        
    finally:
        connection.close()






