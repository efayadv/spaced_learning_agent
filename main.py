from database import initialize_database
from datetime import datetime
from tools import (
    add_review_item,
    get_due_items,
    complete_review,
    start_study_session,
    get_active_study_session,
    finish_study_session,
)
from agent import run_coach

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

    due = datetime.fromisoformat(result["next_due_at"]).astimezone()

    print(f"\nReview saved! Rating: {result['rating']}")
    print(f"Next review: {due.strftime('%b %d, %Y at %I:%M %p %Z')}")


def main():
    initialize_database()

    while True:
        print("\nInterview Coach")

        active = get_active_study_session()

        if active:
            print(
                f"Active session: #{active['id']} — {active['topic']}"
            )

        print("1. Add a learning item")
        print("2. Show due items")
        print("3. Complete a review")
        print("4. Start studying")
        print("5. Finish studying")
        print("6. Exit")
        print("7. Discuss a completed session with the AI coach")


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
                review_item()

            elif choice == "4":
                topic = input("What are you studying? ")
                session = start_study_session(topic)

                print(
                    f"Started session #{session['session_id']} "
                    f"on {session['topic']}."
                )
                print(
                    "Study your material, then choose "
                    "'Finish studying' when you're done."
                )

            elif choice == "5":
                if get_active_study_session() is None:
                    print("There is no active study session.")
                    continue

                print(
                    "Describe what you covered. Include specific "
                    "concepts, examples, or anything confusing."
                )
                print("Enter a blank line to finish your notes.")

                lines = []

                while True:
                    line = input()
                    if not line.strip():
                        break
                    lines.append(line)

                result = finish_study_session("\n".join(lines))

                print(
                    f"Saved session #{result['session_id']}. "
                    f"Elapsed time: {result['elapsed_minutes']:.1f} minutes."
                )
                print("Notes saved. Assessment is pending.")

            elif choice == "6":
                if active:
                    print(
                        "Your study session remains active. "
                        "Reopen the app to finish it."
                    )
                break

            elif choice == "7":
                session_id = int(input("Completed study session ID: "))
                run_coach(session_id)

            else:
                print("Please choose an option from 1 to 7.")

        except ValueError as error:
            print(error)


if __name__ == "__main__":
    main()