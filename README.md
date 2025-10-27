# AI-Meeting-Task-Scheduling-Assistant# Fireflies → AI Agent → Tasks & Notifications (Python)

This project reproduces the n8n workflow that:
- Receives meeting transcripts from Fireflies
- Uses an AI agent to extract action items, create tasks, and notify clients
- Optionally schedules follow-up meetings via Google Calendar

## Files
- `fireflies_ai_tasks.py` — main orchestrator
- `config.py` — loads env and toggles mock/real mode
- `requirements.txt` — pip dependencies
- `.env.example` — env template
- `README.md` — this document

## Quick start (mock mode)
1. Create venv and install:
```bash
python -m venv venv
source venv/bin/activate   # macOS / Linux
venv\Scripts\activate      # Windows
pip install -r requirements.txt
Copy .env.example to .env (optional)

bash
Copy code
cp .env.example .env
Run locally with mock data:

bash
Copy code
python fireflies_ai_tasks.py
Or provide a local test payload:

bash
Copy code
TEST_MEETING_JSON=./sample_payload.json python fireflies_ai_tasks.py
To run with real services
You will need to:

Add OpenAI key (OPENAI_API_KEY) — script will switch out of mock mode if present.

For Fireflies: put FIREFLIES_API_KEY (GraphQL access) and update fetch_transcript_from_fireflies.

For Airtable: generate AIRTABLE_API_KEY, set AIRTABLE_BASE_ID and optionally AIRTABLE_TABLE.

For Gmail: implement OAuth2 flow, replace send_gmail_notification with real Google API client.

For Google Calendar: set GOOGLE_API_TOKEN and GOOGLE_CALENDAR_ID and ensure scope includes calendar events.

Implementation notes & TODOs
OpenAI output parsing: real LLM output may include extra text — current code tries strict JSON from the model. Consider using function-calling, structured JSON schema, or more robust parsing/validation.

Add retries, rate-limit handling, and backoff for production HTTP calls.

Secure secrets (don't commit .env to git).

Add unit tests and CI pipeline (GitHub Actions).
