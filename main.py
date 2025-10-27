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


# ----------------- Google Calendar Event Creation --------------
