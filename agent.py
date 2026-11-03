import json
import os
from pathlib import Path

from datetime import datetime
from scheduler import REVIEW_TIMEZONE
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from tools import (
    save_notes,
    complete_review,
    get_due_items,
    get_item_history,
    )


GENERAL_INSTRUCTIONS = """
You are a personal programming study coach.

When asked what is due now, call get_due_items and answer from its result.
If there are no due items, say so. The tool does not show future reviews.
If the learner only asks for a list, show the list and wait.

When the learner asks to practice a due item, use its learning objective
to ask one question at a time. Wait for an answer before giving feedback.
If the answer is unclear, ask a neutral follow-up. After an actual attempt,
use record_review with the question, the learner's answer, feedback, and
a suggested rating: 1 Again, 2 Hard, 3 Good, or 4 Easy.
The terminal collects the learner's final rating.
Only report a saved review or next date when the tool confirms it.

When the learner wants to save new notes, ask for the notes if missing.
Use their supplied notes verbatim, choose a concise topic (ask if unclear),
and derive 1–5 concrete learning objectives grounded in those notes.
Call save_notes with the topic, original notes, and objectives. The terminal
asks for approval before saving. Do not require starting or ending a study session.
Only claim notes were saved when the tool confirms it. Do not quiz unless asked.
You can save notes, look up due items, and conduct reviews.
You cannot yet search stored notes or look up future dates.
"""

REVIEW_INSTRUCTIONS = """
You are conducting a spaced repetition review of due learning items.

Use the provided items and their histories to conduct the session.
Do not create new review items during this workflow.

For each item:
1. Ask one question testing its learning objective.
2. Keep difficulty comparable to previous reviews.
3. Wait for the user's answer before revealing explanations.
4. If the answer is ambiguous, ask a neutral clarification.
5. Give concise feedback.
6. Call record_review with the actual question, answer, feedback,
   item ID, and suggested rating.

Ratings:
1 = Again: failed recall or needed the answer revealed.
2 = Hard: correct recall with serious difficulty.
3 = Good: correct recall with normal effort.
4 = Easy: effortless correct recall.

The terminal tool handler collects the user's confirmed rating.
Use the saved rating and next due date returned by the tool.
Report returned dates in America/Chicago using 12-hour time and the timezone abbreviation.

Do not reveal previous answers before the user attempts the question.
Do not count repeating your explanation as independent recall.
Do not record the same item twice in this conversation.
If a review is skipped, leave its schedule unchanged.
After all items are handled, summarize and tell the user they can exit.

You cannot send reminders or execute code.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "save_notes",
        "description": (
            "Save the learner's original notes and 1–5 derived review objectives. "
            "The application asks for approval. Identical notes under the same "
            "topic return the existing batch."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "notes": {"type": "string"},
                "objectives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5,
                }
            },
            "required": ["topic", "notes", "objectives"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "record_review",
        "description": (
            "Save an actual assessment attempt for a saved item. "
            "The application displays the attempt and asks the user "
            "to confirm or correct the rating before updating FSRS. "
            "Call only after the user has answered."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "question": {"type": "string"},
                "answer": {"type": "string"},
                "feedback": {"type": "string"},
                "suggested_rating": {
                    "type": "integer",
                    "enum": [1, 2, 3, 4],
                },
            },
            "required": [
                "item_id",
                "question",
                "answer",
                "feedback",
                "suggested_rating",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_due_items",
        "description": (
            "Retrieve learning items due now, including overdue items. "
            "Use when the learner asks what is due or wants to review due items. "
            "This lookup does not start a quiz or change the schedule."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

def run_agent():
    print("\nStudy Coach")
    print("What would you like to do? Try “What's due?”, “Quiz me”, or “Save these notes: ...”")

    first_message = input("\nYou: ").strip()
    if not first_message or first_message.lower() == "exit":
        return

    run_conversation(
        context={},
        instructions=GENERAL_INSTRUCTIONS,
        allowed_item_ids=set(),
        first_message=first_message,
    )

def run_conversation(
    context: dict,
    instructions: str,
    allowed_item_ids: set[int],
    first_message: str | None = None,
):
    load_dotenv(Path(__file__).resolve().parent / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Add OPENAI_API_KEY to your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    general_chat = first_message is not None

    tool_names = {"record_review"}

    if general_chat:
        tool_names.update({"get_due_items", "save_notes"})

    enabled_tools = [
        tool for tool in TOOL_DEFINITIONS
        if tool["name"] in tool_names
    ]

    instructions += "\nReview window: every day, 12:00 PM–10:00 PM America/Chicago. Convert UTC tool dates to this timezone when reporting them.\n"

    if general_chat:
        messages = [{"role": "user", "content": first_message}]
    else:
        messages = [{
            "role": "user",
            "content": (
                "Use this study context to begin:\n"
                + json.dumps(context, ensure_ascii=False)
            ),
        }]

    # Copy the set so changes stay local to this conversation.
    allowed_item_ids = set(allowed_item_ids)
    recorded_items = {}
    tool_rounds = 0

    print("\nCoach conversation. Type 'exit' to return to the menu.")
    print("Saved items and confirmed reviews persist; full chat does not.")

    with OpenAI(timeout=60.0, max_retries=1) as client:
        while True:
            try:
                response = client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=messages,
                    tools=enabled_tools,
                    parallel_tool_calls=False,
                    max_output_tokens=2000,
                    store=False,
                )
            except OpenAIError as error:
                print(f"\nOpenAI request failed: {error}")
                print("Previously saved changes remain in the database.")
                return

            if response.status != "completed":
                print("The response did not finish. Please reopen the coach.")
                return

            messages.extend(response.output)

            if response.output_text:
                print(f"\nCoach: {response.output_text}")

            calls = [
                item
                for item in response.output
                if item.type == "function_call"
            ]

            if calls:
                tool_rounds += 1

                if tool_rounds > 5:
                    print("Tool-call limit reached. Please reopen the coach.")
                    return

                for call in calls:
                    result = execute_tool(
                        call=call,
                        allow_notes=general_chat,
                        allowed_item_ids=allowed_item_ids,
                        recorded_items=recorded_items,
                    )

                    messages.append({
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    })

                # Send the tool results back to the model.
                continue

            tool_rounds = 0

            if not response.output_text:
                print("No text response was returned.")
                return

            while True:
                user_message = input("\nYou: ").strip()
                if user_message:
                    break

            if user_message.lower() == "exit":
                return

            messages.append({
                "role": "user",
                "content": user_message,
            })

def run_due_reviews():
    due_items = get_due_items()

    if not due_items:
        print("No reviews are due")
        return

    for item in due_items:
        item["history"] = get_item_history(item["id"])

    allowed_item_ids = {item["id"] for item in due_items}

    context = {
        "mode": "due_reviews",
        "items": due_items,
    }

    run_conversation(
        context=context,
        instructions=REVIEW_INSTRUCTIONS,
        allowed_item_ids=allowed_item_ids,
    )


def handle_record_review(arguments, allowed_item_ids, recorded_items):
    required = {
        "item_id",
        "question",
        "answer",
        "feedback",
        "suggested_rating",
    }

    if not isinstance(arguments, dict) or set(arguments) != required:
        raise ValueError("Invalid review arguments.")

    item_id = arguments["item_id"]
    suggested = arguments["suggested_rating"]

    if type(item_id) is not int:
        raise ValueError("Item ID must be an integer.")

    if type(suggested) is not int or suggested not in (1, 2, 3, 4):
        raise ValueError("Invalid suggested rating.")

    for field in ("question", "answer", "feedback"):
        value = arguments[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} cannot be empty.")

    # The model may only review items available in this conversation.
    if item_id not in allowed_item_ids:
        raise ValueError("This item is not available in the current conversation.")

    # Avoid grading the same item twice in this coach conversation.
    if item_id in recorded_items:
        return {
            **recorded_items[item_id],
            "status": "already_recorded",
        }

    print(f"\nReview item #{item_id}")
    print(f"\nQuestion: {arguments['question']}")
    print(f"Your answer: {arguments['answer']}")
    print(f"Feedback: {arguments['feedback']}")

    print("\n1. Again — Could not recall")
    print("2. Hard — Correct recall with serious difficulty")
    print("3. Good — Correct recall with normal effort")
    print("4. Easy — Effortless correct recall")
    print(f"Coach suggests: {suggested}")

    while True:
        choice = input(
            "Enter rating 1–4 to save, or 'skip' to leave unchanged: "
        ).strip().lower()

        if choice == "skip":
            return {
                "status": "skipped",
                "message": "No attempt saved; the due date is unchanged.",
            }

        if choice in {"1", "2", "3", "4"}:
            confirmed_rating = int(choice)
            break

        print("Choose 1, 2, 3, 4, or skip.")

    result = complete_review(
        item_id=item_id,
        answer=arguments["answer"],
        rating_value=confirmed_rating,
        question=arguments["question"],
        feedback=arguments["feedback"],
    )

    recorded_items[item_id] = result

    due = datetime.fromisoformat(result["next_due_at"]).astimezone(REVIEW_TIMEZONE)

    print(f"\nReview saved as {result['rating']}.")
    print(f"Next review: {due.strftime('%b %d, %Y at %I:%M %p %Z')}")

    return result

def execute_tool(
    call,
    allow_notes: bool,
    allowed_item_ids: set[int],
    recorded_items: dict,
):
    try:
        arguments = json.loads(call.arguments)

        if call.name == "get_due_items":
            if arguments != {}:
                raise ValueError("get_due_items takes no arguments.")

            print("[tool] get_due_items")
            items = get_due_items()
            allowed_item_ids.update(item["id"] for item in items)
            return {"items": items}

        if call.name == "record_review":
            return handle_record_review(
                arguments,
                allowed_item_ids,
                recorded_items,
            )

        if call.name != "save_notes":
            raise ValueError("Unknown tool.")

        if not allow_notes:
            raise ValueError(
                "Creating items is not allowed during due reviews."
            )

        if (
            not isinstance(arguments, dict)
            or set(arguments) != {"topic", "notes", "objectives"}
        ):
            raise ValueError("Invalid tool arguments.")

        objectives = arguments["objectives"]

        if (
            not isinstance(objectives, list)
            or not 1 <= len(objectives) <= 5
            or any(
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 500
                for value in objectives
            )
        ):
            raise ValueError("Invalid learning objectives.")

        for field in ("topic", "notes"):
            if not isinstance(arguments[field], str) or not arguments[field].strip():
                raise ValueError(f"{field} cannot be empty.")

        print(f"\nTopic: {arguments['topic']}")
        print(f"Notes: {arguments['notes']}")
        print("\nReview objectives:")

        for index, objective in enumerate(objectives, start=1):
            print(f"{index}. {objective}")

        approval = input("\nSave these notes and review items? [y/N]: ").strip().lower()

        if approval != "y":
            return {
                "status": "declined",
                "message": "Nothing was saved. Ask what should change.",
            }

        result = save_notes(arguments["topic"], arguments["notes"], objectives)

        # Newly saved items can now be assessed in this conversation.
        allowed_item_ids.update(
            item["id"] for item in result["items"]
        )

        print(f"\nDatabase result: {result['status']}")

        return result

    except (ValueError, TypeError) as error:
        return {"status": "error", "message": str(error)}