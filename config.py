"""
Configuration loader for Fireflies AI Agent project.
Put real credentials into a .env file or environment variables.
If critical keys are missing, the project runs in MOCK mode.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # Fireflies
    FIREFLIES_API_KEY: str

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str

    # Airtable
    AIRTABLE_API_KEY: str
    AIRTABLE_BASE_ID: str
    AIRTABLE_TABLE: str

    # Gmail (simple bearer token placeholder for demo)
    GMAIL_OAUTH_BEARER: str

    # Google Calendar
    GOOGLE_API_TOKEN: str
    GOOGLE_CALENDAR_ID: str

    # Agent identity (so LLM knows "me")
    MY_EMAIL: str
    MY_NAME: str

    # Misc
    mock: bool

    @staticmethod
    def load_from_env() -> "Config":
        fi = os.getenv("FIREFLIES_API_KEY", "")
        oa = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        at_key = os.getenv("AIRTABLE_API_KEY", "")
        at_base = os.getenv("AIRTABLE_BASE_ID", "")
        at_table = os.getenv("AIRTABLE_TABLE", "Tasks")
        gmail_bearer = os.getenv("GMAIL_OAUTH_BEARER", "")
        gtoken = os.getenv("GOOGLE_API_TOKEN", "")
        gcal = os.getenv("GOOGLE_CALENDAR_ID", "")
        my_email = os.getenv("MY_EMAIL", "")
        my_name = os.getenv("MY_NAME", "")

        # If any core key missing, enable mock mode
        core_present = all([oa])
        mock = not core_present

        return Config(
            FIREFLIES_API_KEY=fi,
            OPENAI_API_KEY=oa,
            OPENAI_MODEL=model,
            AIRTABLE_API_KEY=at_key,
            AIRTABLE_BASE_ID=at_base,
            AIRTABLE_TABLE=at_table,
            GMAIL_OAUTH_BEARER=gmail_bearer,
            GOOGLE_API_TOKEN=gtoken,
            GOOGLE_CALENDAR_ID=gcal,
            MY_EMAIL=my_email,
            MY_NAME=my_name,
            mock=mock,
        )
