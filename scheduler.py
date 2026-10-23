from fsrs import Scheduler, Card, Rating, ReviewLog
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

REVIEW_TIMEZONE = ZoneInfo("America/Chicago")

def fit_review_window(due: datetime) -> datetime:
    """Move out-of-window times forward to the next local noon."""
    if due.tzinfo is None:
        raise ValueError("Review dates must include a timezone.")
    local = due.astimezone(REVIEW_TIMEZONE)
    if local.time() < time(12):
        local = datetime.combine(local.date(), time(12), REVIEW_TIMEZONE)
    elif local.time() > time(22):
        local = datetime.combine(local.date() + timedelta(days=1), time(12), REVIEW_TIMEZONE)
    return local.astimezone(timezone.utc)


scheduler = Scheduler(
    parameters = (
            0.212,
            1.2931,
            2.3065,
            8.2956,
            6.4133,
            0.8334,
            3.0194,
            0.001,
            1.8722,
            0.1666,
            0.796,
            1.4835,
            0.0614,
            0.2629,
            1.6483,
            0.6014,
            1.8729,
            0.5425,
            0.0912,
            0.0658,
            0.1542,
    ),
    desired_retention = 0.9,
    learning_steps = (),
    relearning_steps = (),
    maximum_interval = 30,
    enable_fuzzing = False
)

def schedule_next_review(card: Card, rating: Rating):
    updated_card, review_log = scheduler.review_card(card, rating)
    updated_card.due = fit_review_window(updated_card.due)
    return updated_card, review_log
