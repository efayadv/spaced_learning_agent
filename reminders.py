from database import get_connection
import re
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import subprocess

def get_reminder_settings():
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT 
                id, 
                enabled, 
                daily_time, 
                followup_enabled,
                followup_time,
                timezone
            FROM reminder_settings
            WHERE id = 1
            """
        ).fetchone()

        if not row:
            raise ValueError("reminder_settings is not initialized")

        settings = dict(row)
        settings["enabled"] = bool(settings["enabled"])
        settings["followup_enabled"] = bool(settings["followup_enabled"])
        return settings

    finally:
        connection.close()



def update_reminder_settings(
    *,
    enabled: bool,
    daily_time: str,
    followup_enabled: bool,
    followup_time: str,
    timezone: str,
):

    #input validation
    if not isinstance(enabled, bool) or not isinstance(followup_enabled, bool):
        raise ValueError("Flags must be boolean")

    if not isinstance(daily_time, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", daily_time):
        raise ValueError("Daily time must use HH:MM, such as 12:00 or 19:30.")
    try:
        parsed_daily = time.fromisoformat(daily_time)
    except ValueError:
        raise ValueError("Daily time must be a valid clock time.") from None
    if not time(12, 0) <= parsed_daily <= time(22, 0):
        raise ValueError("Daily time must be between 12:00 and 22:00.")

    if not isinstance(followup_time, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", followup_time):
        raise ValueError("Follow-up time must use HH:MM, such as 12:00 or 19:30.")
    try:
        parsed_followup = time.fromisoformat(followup_time)
    except ValueError:
        raise ValueError("Follow-up time must be a valid clock time.") from None
    if not time(12, 0) <= parsed_followup <= time(22, 0):
        raise ValueError("Follow-up time must be between 12:00 and 22:00.")

    if parsed_followup <= parsed_daily:
        raise ValueError("Follow-up time must be later than daily time.")

    if not isinstance(timezone, str) or not timezone.strip():
        raise ValueError("Timezone must be a valid timezone name, such as America/Chicago.")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Timezone must be a valid timezone name, such as America/Chicago.") from None

    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute(
                """
                UPDATE reminder_settings
                SET enabled = ?, daily_time = ?, followup_enabled = ?, followup_time = ?, timezone = ?
                WHERE id = 1
                """,
                (
                    enabled,
                    daily_time,
                    followup_enabled,
                    followup_time,
                    timezone,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("reminder_settings is not initialized")

    finally:
        connection.close()


def send_notification(title: str, message: str):
    script = """
    on run argv
        display notification (item 2 of argv) with title (item 1 of argv)
    end run
    """

    subprocess.run(
        ["/usr/bin/osascript", "-e", script, title, message],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


def check_reminders(now=None):
    pass

