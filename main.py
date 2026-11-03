import sys
from database import initialize_database
from datetime import datetime
from scheduler import REVIEW_TIMEZONE
from tools import (
    add_review_item,
    get_due_items,
    complete_review,
)
from agent import run_agent, run_due_reviews

def show_due_items(items):
    for item in items:
        print(
            f"\n#{item['id']} — {item['topic']}\n"
            f"  {item['learning_objective']}"
        )

def review_item():
    items = get_due_items()

    if not items:
        print("No items available")
        return

    show_due_items(items)

    try:
        item_id = int(input("\nEnter an item ID to review: "))
    except ValueError:
        print("Please enter valid numeric Id")
        return

    selected = next(
        (item for item in items if item["id"] == item_id),
        None,
    )

    if selected is None:
        print("Please choose one of the displayed items")
        return

    print(f"\nExplain or demonstrate: {selected['learning_objective']}")
    answer = input("Your answer: ").strip()

    print("\nHow well did you recall it?")
    print("1. Again — Could not recall it")
    print("2. Hard — Recalled it with serious difficulty")
    print("3. Good — Recalled it with some hesitation")
    print("4. Easy — Recalled it easily")

    try:
        rating = int(input("Rating: "))
        result = complete_review(item_id, answer, rating)
    except ValueError as error:
        print(f"Could not save review: {error}")
        return

    due = datetime.fromisoformat(result["next_due_at"]).astimezone(REVIEW_TIMEZONE)

    print(f"\nReview saved! Rating: {result['rating']}")
    print(f"Next review: {due.strftime('%b %d, %Y at %I:%M %p %Z')}")


def main():
    initialize_database()

    while True:
        print("--------------------------------")
        print("\nInterview Coach")

        print("1. Add a learning item")
        print("2. Show due items")
        print("3. Review due items with AI coach")
        print("4. Chat with the AI coach / save notes")
        print("5. Exit")

        choice = input("Choose an option: ").strip()

        try:
            if choice == "1":
                topic = input("Topic: ")
                objective = input(
                    "What should you be able to explain or do? "
                )

                item_id = add_review_item(topic, objective)
                print(f"Created learning item #{item_id}.")

            elif choice == "2":
                items = get_due_items()

                if items:
                    show_due_items(items)
                else:
                    print("No reviews are due.")

            elif choice == "3":
                run_due_reviews()

            elif choice == "4":
                run_agent()

            elif choice == "5":
                break

            else:
                print("Please choose an option from 1 to 5.")

        except ValueError as error:
            print(error)


if __name__ == "__main__":
    if "--menu" in sys.argv:
        main()
    else:
        initialize_database()
        run_agent()