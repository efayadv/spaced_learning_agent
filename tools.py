from datetime import datetime, timezone
from scheduler import schedule_next_review
from database import get_connection
from fsrs import Card, Rating


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

            cursor = connection.execute(
                """
                INSERT INTO review_items (
                    topic_id,
                    learning_objective,
                    fsrs_card_json,
                    next_due_at
                ) 
                VALUES (?, ?, ?, ?)
                """,
                (
                    topic["id"],
                    learning_objective,
                    card.to_json(),
                    card.due.isoformat(),  
                ),
            )

            return cursor.lastrowid
        
    finally:
        connection.close()

def complete_review(item_id: int, answer: str, rating_value: int ):
    if rating_value not in (1, 2, 3, 4):
        raise ValueError("Rating must be between 1 and 4")

    if not answer.strip():
        raise ValueError("Answer cannot be empty")

    connection = get_connection()

    try:
        with connection:
            item = connection.execute(
                """
                SELECT learning_objective, fsrs_card_json
                FROM review_items
                WHERE id = ?
                """,
                (item_id,),
            ).fetchone()

            if item is None:
                raise ValueError("Learning item not found.")

            card = Card.from_json(item["fsrs_card_json"])
            rating = Rating(rating_value)

            updated_card, review_log = schedule_next_review(card, rating)
            #save new state and due date
            connection.execute(
                """
                UPDATE review_items
                SET fsrs_card_json = ?, next_due_at = ?
                WHERE id = ?
                """,
                (
                    updated_card.to_json(),
                    updated_card.due.isoformat(),
                    item_id,
                ),
            )

            # Keep a permanent record of this attempt
            connection.execute(
                """
                INSERT INTO attempts (
                    review_item_id,
                    question,
                    answer,
                    feedback,
                    fsrs_review_log_json,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item["learning_objective"],
                    answer.strip(),
                    f"Self-assessed: {rating.name}",
                    review_log.to_json(),
                    review_log.review_datetime.isoformat(),
                ),
            )

            return {
                "item_id": item_id,
                "rating": rating.name,
                "next_due_at": updated_card.due.isoformat(),
            }
    finally:
        connection.close()


def get_due_items():
    now = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                review_items.id,
                topics.name AS topic,
                review_items.learning_objective,
                review_items.next_due_at
            FROM review_items
            JOIN topics ON topics.id = review_items.topic_id
            WHERE review_items.next_due_at <= ?
            ORDER BY review_items.next_due_at
            """,
            (now,),
        ).fetchall()

        return [dict(row) for row in rows]        
    finally:
        connection.close()






