from fsrs import Scheduler, Card, Rating, ReviewLog
from datetime import timedelta

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
    learning_steps = (timedelta(minutes=1), timedelta(minutes=10)),
    relearning_steps = (timedelta(minutes=10),),
    maximum_interval = 30,
    enable_fuzzing = False
)


def schedule_next_review(card: Card, rating: Rating):
    updated_card, review_log = scheduler.review_card(card, rating)
    return updated_card, review_log




