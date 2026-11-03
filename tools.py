from datetime import datetime, timezone, timedelta
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

def complete_review(
        item_id: int, 
        answer: str, 
        rating_value: int,
        question: str | None = None,
        feedback: str | None = None,
    ):
    if rating_value not in (1, 2, 3, 4):
        raise ValueError("Rating must be between 1 and 4")

    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Answer cannot be empty.")

    if question is None and (not isinstance(question, str) or not question.strip()):
        raise ValueError("Question cannot be empty")

    if feedback is None and (not isinstance(feedback, str) or not feedback.strip()):
        raise ValueError("Feedback cannot be empty")

    connection = get_connection()

    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

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
                    question.strip() if question else item["learning_objective"],
                    answer.strip(),
                    feedback.strip() if feedback else f"Self-assessed: {rating.name}",
                    review_log.to_json(),
                    review_log.review_datetime.isoformat(),
                ),
            )

            return {
                "status": "saved",
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

def save_notes(topic: str, notes: str, objectives: list[str]):
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Topic cannot be empty.")
    if not isinstance(notes, str) or not notes.strip():
        raise ValueError("Notes cannot be empty.")
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 5:
        raise ValueError("Provide between 1 and 5 objectives.")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 500
           for value in objectives):
        raise ValueError("Objectives must be nonempty and at most 500 characters.")
    objectives = [value.strip() for value in objectives]
    if len({value.casefold() for value in objectives}) != len(objectives):
        raise ValueError("Remove duplicate objectives.")

    connection = get_connection()
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic.strip(),))
            topic_id = connection.execute(
                "SELECT id FROM topics WHERE name = ?", (topic.strip(),)
            ).fetchone()["id"]
            existing = connection.execute(
                "SELECT id FROM notes WHERE topic_id = ? AND content = ?",
                (topic_id, notes.strip()),
            ).fetchone()
            if existing:
                note_id = existing["id"]
                status = "already_saved"
            else:
                note_id = connection.execute(
                    "INSERT INTO notes (topic_id, content, created_at) VALUES (?, ?, ?)",
                    (topic_id, notes.strip(), datetime.now(timezone.utc).isoformat()),
                ).lastrowid
                first_due = datetime.now(timezone.utc) + timedelta(days=1)
                for objective in objectives:
                    card = Card()
                    card.due = first_due
                    item_id = connection.execute(
                        """INSERT INTO review_items
                           (topic_id, learning_objective, fsrs_card_json, next_due_at)
                           VALUES (?, ?, ?, ?)""",
                        (topic_id, objective, card.to_json(), card.due.isoformat()),
                    ).lastrowid
                    connection.execute(
                        "INSERT INTO note_review_items (note_id, review_item_id) VALUES (?, ?)",
                        (note_id, item_id),
                    )
                status = "saved"
            rows = connection.execute(
                """SELECT r.id, r.learning_objective, r.next_due_at
                   FROM review_items AS r JOIN note_review_items AS link
                   ON link.review_item_id = r.id WHERE link.note_id = ? ORDER BY r.id""",
                (note_id,),
            ).fetchall()
            return {"status": status, "note_id": note_id, "items": [dict(row) for row in rows]}
    finally:
        connection.close()


def get_item_history(item_id: int):
    # Retrieve previous questions, answers, and feedback
    connection = get_connection()
    try:
        item = connection.execute(
            """
            SELECT id 
            FROM review_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

        if item is None:
            raise ValueError("No review item found with this id")

        #from attempts
        attempts = connection.execute(
            """
            SELECT
                question,
                answer,
                feedback,
                reviewed_at
            FROM attempts
            WHERE review_item_id = ?
            ORDER BY reviewed_at DESC, id DESC
            """,
            (item_id,),
        ).fetchall()

        return [dict(attempt) for attempt in attempts]    

        #we are to retrieve previous question, answers and feedback from attempts
    finally:
        connection.close()


def get_upcoming_reviews(days: int):
    if type(days) is not int or not 1 <= days <= 90:
        raise ValueError("Choose a range between 1 and 90 days.")

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT r.id, t.name AS topic,
                   r.learning_objective, r.next_due_at
            FROM review_items AS r
            JOIN topics AS t ON t.id = r.topic_id
            WHERE r.next_due_at > ? AND r.next_due_at <= ?
            ORDER BY r.next_due_at, r.id
            """,
            (now.isoformat(), end.isoformat()),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()

'''
This function is able to get notes and topics
'''
def find_notes(topic: str):
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Provide a topic or keyword.")

    keyword = topic.strip()
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT s.id AS note_id, t.name AS topic,
                   s.created_at, s.content AS notes
            FROM notes AS s
            JOIN topics AS t ON t.id = s.topic_id
            WHERE (
                  instr(lower(t.name), lower(?)) > 0
                  OR instr(lower(s.content), lower(?)) > 0
              )
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT 5
            """,
            (keyword, keyword),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()












