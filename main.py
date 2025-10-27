#!/usr/bin/env python3
"""
Fireflies AI Agent → Tasks & Notification
-----------------------------------------
Behavior:
- Receives webhook payloads (Fireflies meeting transcript metadata)
- Fetches full transcript via Fireflies GraphQL API (or uses mock data)
- Sends transcript to OpenAI for analysis (extract tasks, client actions, follow-up meeting)
- Creates tasks in Airtable (or mocks)
- Sends notification emails to clients via Gmail (or mocks)
- Creates Google Meet events if agent requests (or mocks)

Notes:
- This is mock-first. If environment variables for real services are present, the script will attempt real calls.
- Replace placeholders and implement OAuth flows for production use (Gmail/Airtable/Google Calendar/Fireflies).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests

# optional import; if not installed, code relies on requests and mock mode
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from config import Config

log = logging.getLogger("fireflies_ai_tasks")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
cfg = Config.load_from_env()


# ----------------- Helpers / Mock data -----------------
def mock_fireflies_transcript(meeting_id: str) -> Dict[str, Any]:
    return {
        "id": meeting_id,
        "title": "Project Phoenix kickoff",
        "participants": ["alice@example.com", "bob@example.com", cfg.MY_EMAIL or "me@example.com"],
        "sentences": [
            {"speaker_name": "Alice", "text": "We need to deliver the prototype by next Friday."},
            {"speaker_name": "Bob", "text": "I'll take the data pipeline action."},
            {"speaker_name": cfg.MY_NAME or "Me", "text": "I'll prepare the summary and arrange follow-up call."},
        ],
        "summary": {"bullet_gist": "Prototype due next Friday. Bob owns data pipeline. Follow-up call needed."}
    }


def openai_client():
    if cfg.mock or OpenAI is None:
        return None
    return OpenAI(api_key=cfg.OPENAI_API_KEY)


# ----------------- Fireflies API -----------------
def fetch_transcript_from_fireflies(meeting_id: str) -> Dict[str, Any]:
    """Fetch transcript via Fireflies GraphQL API. If no API key, return mock."""
    if cfg.mock or not cfg.FIREFLIES_API_KEY:
        log.info("[MOCK] Fetching transcript from Fireflies")
        return mock_fireflies_transcript(meeting_id)

    url = "https://api.fireflies.ai/graphql"
    headers = {"Authorization": f"Bearer {cfg.FIREFLIES_API_KEY}", "Content-Type": "application/json"}
    query = """
    query Transcript($transcriptId: String!) {
      transcript(id: $transcriptId) {
        title
        participants
        sentences { speaker_name text }
        summary { bullet_gist }
      }
    }
    """
    body = {"query": query, "variables": {"transcriptId": meeting_id}}
    r = requests.post(url, json=body, headers=headers)
    r.raise_for_status()
    data = r.json()
    # normalize to expected shape
    transcript = data.get("data", {}).get("transcript", {})
    if not transcript:
        raise RuntimeError("Empty transcript returned from Fireflies.")
    return {
        "id": meeting_id,
        "title": transcript.get("title"),
        "participants": transcript.get("participants"),
        "sentences": transcript.get("sentences"),
        "summary": transcript.get("summary"),
    }


# ----------------- OpenAI Analysis -----------------
def analyze_transcript_with_openai(transcript: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ask the LLM to:
      - extract action items (tasks) for 'me' (cfg.MY_EMAIL / cfg.MY_NAME)
      - extract action items assigned to participants
      - determine if a follow-up meeting is needed (and propose date/time)
      - produce a structured JSON with keys: tasks_for_me, participant_tasks, notify_items, follow_up (optional)
    """
    if cfg.mock or OpenAI is None:
        log.info("[MOCK] Analyzing transcript with OpenAI")
        # produce structure matching expected output
        return {
            "tasks_for_me": [
                {
                    "name": "Prepare summary and slides",
                    "description": "Draft meeting summary + slides for prototype demo",
                    "due_date": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
                    "priority": "High",
                    "project_name": "Phoenix"
                }
            ],
            "participant_tasks": [
                {
                    "participant_email": "bob@example.com",
                    "tasks": [
                        {
                            "name": "Build data pipeline",
                            "description": "Create dataset ingestion for prototype",
                            "due_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                            "priority": "Urgent",
                            "project_name": "Phoenix"
                        }
                    ]
                }
            ],
            "notify_items": [
                {
                    "participant_email": "bob@example.com",
                    "message": "You have been assigned: Build data pipeline. Due in 7 days."
                }
            ],
            "follow_up": {
                "required": True,
                "suggested_start": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT10:00:00"),
                "suggested_end": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT10:30:00"),
                "attendee_email": "alice@example.com",
                "meeting_name": "Follow-up: Project Phoenix"
            }
        }

    # Real OpenAI call
    client = openai_client()
    prompt = (
        "You are an assistant that converts a meeting transcript into structured follow-up items.\n\n"
        "Return valid JSON with keys: tasks_for_me (array), participant_tasks (array of {participant_email, tasks}), "
        "notify_items (array of {participant_email, message}), follow_up (object or null).\n\n"
        f"MY_EMAIL: {cfg.MY_EMAIL}\nMY_NAME: {cfg.MY_NAME}\n\nTranscript JSON:\n{json.dumps(transcript)}\n\n"
        "Only include tasks assigned to me in tasks_for_me. Participant tasks should only include tasks for other participants."
    )

    res = client.chat.completions.create(
        model=cfg.OPENAI_MODEL or "gpt-4o-mini",
        messages=[{"role": "system", "content": "You extract structured follow-up actions from meeting transcripts."},
                  {"role": "user", "content": prompt}],
        temperature=0.0,
    )
    text = res.choices[0].message.content
    try:
        parsed = json.loads(text)
        return parsed
    except Exception:
        # try to extract JSON substring
        import re
        m = re.search(r"(\{.*\})", text, re.S)
        if m:
            return json.loads(m.group(1))
        raise


# ----------------- Airtable Integration -----------------
def create_airtable_tasks(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create tasks in Airtable. Returns list of created records or mock records."""
    if cfg.mock or not (cfg.AIRTABLE_API_KEY and cfg.AIRTABLE_BASE_ID and cfg.AIRTABLE_TABLE):
        log.info("[MOCK] Creating tasks in Airtable")
        created = []
        for it in items:
            created.append({"id": f"mock_{it['name']}", "fields": it})
        return created

    url = f"https://api.airtable.com/v0/{cfg.AIRTABLE_BASE_ID}/{cfg.AIRTABLE_TABLE}"
    headers = {"Authorization": f"Bearer {cfg.AIRTABLE_API_KEY}", "Content-Type": "application/json"}

    created = []
    for it in items:
        body = {"fields": {
            "Name": it["name"],
            "Description": it.get("description", ""),
            "Due Date": it.get("due_date"),
            "Priority": it.get("priority"),
            "Project": [it.get("project_name")] if it.get("project_name") else []
        }}
        r = requests.post(url, json=body, headers=headers)
        r.raise_for_status()
        created.append(r.json())
    return created


# ----------------- Gmail Notification -----------------
def send_gmail_notification(to_email: str, subject: str, body_text: str) -> bool:
    """
    Sends a simple email via Gmail REST API (requires OAuth). For demo we mock if no token.
    Production: use googleapiclient and OAuth2 flow with proper scopes.
    """
    if cfg.mock or not cfg.GMAIL_OAUTH_BEARER:
        log.info(f"[MOCK] Sending Gmail to {to_email}:\nSubject: {subject}\n{body_text}")
        return True

    # Placeholder for real Gmail send (requires proper OAuth2 and base64-encoded raw message)
    log.info("Real Gmail sending is not implemented in this template. Please plug in Google API client flow.")
    return False


# ----------------- Google Calendar Event Creation -----------------
def create_google_calendar_event(summary: str, start_iso: str, end_iso: str, attendees: List[str]) -> Dict[str, Any]:
    if cfg.mock or not (cfg.GOOGLE_API_TOKEN and cfg.GOOGLE_CALENDAR_ID):
        log.info(f"[MOCK] Creating calendar event '{summary}' {start_iso} -> {end_iso} for {attendees}")
        return {"id": "mock_event_1", "htmlLink": "https://calendar.google.com/mock/event123"}

    url = f"https://www.googleapis.com/calendar/v3/calendars/{cfg.GOOGLE_CALENDAR_ID}/events"
    headers = {"Authorization": f"Bearer {cfg.GOOGLE_API_TOKEN}", "Content-Type": "application/json"}
    body = {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "attendees": [{"email": e} for e in attendees],
        "conferenceData": {"createRequest": {"requestId": f"req-{int(datetime.now().timestamp())}","conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    }
    r = requests.post(url, headers=headers, json=body)
    r.raise_for_status()
    return r.json()


# ----------------- Orchestrator -----------------
def process_meeting(meeting_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    meeting_payload is expected to have keys e.g. {"meetingId": "...", "source": "fireflies", ...}
    Returns a summary of actions performed.
    """
    meeting_id = meeting_payload.get("meetingId") or meeting_payload.get("transcriptId") or meeting_payload.get("id") or "demo_meeting_1"
    log.info(f"Processing meeting {meeting_id}")

    transcript = fetch_transcript_from_fireflies(meeting_id)
    analysis = analyze_transcript_with_openai(transcript)

    # Create tasks for "me"
    tasks_created = []
    if analysis.get("tasks_for_me"):
        tasks_created = create_airtable_tasks(analysis["tasks_for_me"])
        log.info(f"Created {len(tasks_created)} tasks for me in Airtable/mock.")

    # Create tasks for participants and notify them
    participant_notifications = []
    for p in analysis.get("participant_tasks", []):
        participant_email = p.get("participant_email")
        tasks = p.get("tasks", [])
        # create tasks assigned to participant? In this example, we store them in the same Airtable table with description containing assignee
        # For simplicity, create and notify
        created = create_airtable_tasks(tasks)
        log.info(f"Created {len(created)} participant tasks for {participant_email}")
        # Send a notification only for that participant's tasks
        message = f"Hello,\n\nHere are your action items from the meeting '{transcript.get('title') }':\n"
        for t in tasks:
            message += f"- {t['name']} (Due {t.get('due_date')})\n  {t.get('description')}\n"
        message += "\nRegards,\nAuto Agent"
        sent = send_gmail_notification(participant_email, f"Action items: {transcript.get('title')}", message)
        participant_notifications.append({"email": participant_email, "sent": sent})

    # Notify clients as instructed in notify_items (AI-provided)
    notify_results = []
    for n in analysis.get("notify_items", []):
        to = n.get("participant_email")
        msg = n.get("message") or n.get("body") or "You have tasks assigned."
        sent = send_gmail_notification(to, f"Tasks from {transcript.get('title')}", msg)
        notify_results.append({"to": to, "sent": sent})

    # If follow-up requested, create a calendar event
    follow_up_result = None
    if analysis.get("follow_up") and analysis["follow_up"].get("required"):
        fu = analysis["follow_up"]
        attendees = [fu.get("attendee_email")] if fu.get("attendee_email") else transcript.get("participants", [])
        created_event = create_google_calendar_event(
            fu.get("meeting_name", f"Follow-up: {transcript.get('title')}"),
            fu.get("suggested_start"),
            fu.get("suggested_end"),
            attendees
        )
        follow_up_result = created_event
        log.info(f"Created follow-up: {created_event.get('htmlLink')}")

    return {
        "meeting_id": meeting_id,
        "tasks_created_for_me": tasks_created,
        "participant_notifications": participant_notifications,
        "notify_results": notify_results,
        "follow_up_result": follow_up_result,
    }


# ----------------- Simple CLI / Webhook Simulation -----------------
def main():
    # For quick testing allow passing a local JSON file or meeting id via env/args
    test_meeting = os.getenv("TEST_MEETING_JSON")
    test_meeting_id = os.getenv("TEST_MEETING_ID")

    if test_meeting:
        with open(test_meeting, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = {"meetingId": test_meeting_id or "demo_meeting_1"}

    result = process_meeting(payload)
    log.info("Processing result:\n" + json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
