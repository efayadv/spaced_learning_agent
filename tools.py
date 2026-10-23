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

def start_study_session(topic_name: str):
    topic_name = topic_name.strip()

    if not topic_name:
        raise ValueError("Topic cannot be empty")

    connection = get_connection()

    try:
        with connection:
            active = connection.execute(
                """
                SELECT id
                FROM study_sessions
                WHERE ended_at IS NULL
                """
            ).fetchone()

            if active is not None:
                raise ValueError(
                    f"Session #{active['id']} is already active. "
                    "Finish it before starting another."
                )

            connection.execute(
                "INSERT OR IGNORE INTO topics (name) VALUES (?)", 
                (topic_name,),
            )

            topic = connection.execute(
                "SELECT id FROM topics WHERE name = ?",
                (topic_name,),
            ).fetchone()

            started_at = datetime.now(timezone.utc).isoformat()

            cursor = connection.execute(
                """
                INSERT INTO study_sessions (topic_id, started_at)
                VALUES (?, ?)
                """,
                (topic["id"], started_at),
            )

            return {
                "session_id": cursor.lastrowid,
                "topic": topic_name,
                "started_at": started_at,
            }
    finally:
        connection.close()



def get_active_study_session():
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                study_sessions.id,
                topics.name AS topic,
                study_sessions.started_at
            FROM study_sessions
            JOIN topics ON topics.id = study_sessions.topic_id
            WHERE study_sessions.ended_at IS NULL
            """
        ).fetchone()

        return dict(row) if row else None
    finally:
        connection.close()

def finish_study_session(notes: str):
    notes = notes.strip()

    if not notes:
        raise ValueError(
            "Describe what you covered so the coach can assess it later."
        )

    connection = get_connection()

    try: 
        with connection:
            session = connection.execute(
                """
                SELECT id, started_at
                FROM study_sessions
                WHERE ended_at is NULL
                """
            ).fetchone()

            if session is None:
                raise ValueError("There is no active study session.")

            ended_at = datetime.now(timezone.utc)
            started_at = datetime.fromisoformat(session["started_at"])

            connection.execute(
                """
                UPDATE study_sessions
                SET ended_at = ?, notes = ?
                WHERE id = ?
                """,
                (ended_at.isoformat(), notes, session["id"]),
            )
            return {
                "session_id": session["id"],
                "elapsed_minutes": (
                    ended_at - started_at
                ).total_seconds() / 60,
                "assessment_status": "pending",
            }

    finally:
        connection.close()

def get_study_session(session_id: id):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
                study_sessions.id,
                topics.name AS topic,
                study_sessions.started_at,
                study_sessions.ended_at,
                study_sessions.notes
            FROM study_sessions
            JOIN topics ON topics.id = study_sessions.topic_id
            WHERE study_sessions.id = ?
            """,
            (session_id,),
        ).fetchone()

        if row is None:
            raise ValueError("Study session not found")

        if row["ended_at"] is None:
            raise ValueError("Finish the study session first")

        return dict(row)
    
    finally:
        connection.close()

def get_session_review_items(session_id: int):
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                r.id,
                r.learning_objective,
                r.next_due_at
            FROM review_items AS r
            JOIN session_review_items AS link
                ON link.review_item_id = r.id
            WHERE link.session_id = ?
            ORDER BY r.id
            """,
            (session_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()

def save_session_review_items(session_id: int, objectives: list[str]):
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 5:
        raise ValueError("Provide between 1 and 5 objectives")

    if any(
        not isinstance(objective, str)
        or not objective.strip()
        or len(objective) > 500
        for objective in objectives
    ):
        raise ValueError("Objectives must be non empty and under 500 characters.")

    objectives = [objective.strip() for objective in objectives]

    if len({objective.casefold() for objective in objectives}) != len(objectives):
        raise ValueError("Remove duplicate objectives")

    connection = get_connection()

    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            session = connection.execute(
                """
                SELECT topic_id, ended_at
                FROM study_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

            if session is None or session["ended_at"] is None:
                raise ValueError("A completed study session is required.")

            existing = connection.execute(
                """
                SELECT r.id, r.learning_objective, r.next_due_at
                FROM review_items AS r
                JOIN session_review_items AS link
                    ON link.review_item_id = r.id
                WHERE link.session_id = ?
                ORDER BY r.id
                """,
                (session_id,),
            ).fetchall()

            if existing:
                return {
                    "status": "already_saved",
                    "items": [dict(row) for row in existing],
                }

            first_due = datetime.now(timezone.utc) + timedelta(days=1)
            saved = []

            for objective in objectives:
                card = Card()
                card.due = first_due

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
                        session["topic_id"],
                        objective,
                        card.to_json(),
                        card.due.isoformat(),
                    ),
                )

                item_id = cursor.lastrowid

                connection.execute(
                    """
                    INSERT INTO session_review_items (
                        session_id,
                        review_item_id
                    ) VALUES (?, ?)
                    """,
                    (
                        session_id,
                        item_id
                    ),
                )

                saved.append({
                    "id": item_id,
                    "learning_objective": objective,
                    "next_due_at": card.due.isoformat(),
                })

            return {"status": "saved", "items": saved}
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











