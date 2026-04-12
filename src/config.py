"""Configuration loader."""

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    config["_env"] = {
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "bland_api_key": os.getenv("BLAND_API_KEY", ""),
        "twilio_account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "twilio_auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "sendgrid_api_key": os.getenv("SENDGRID_API_KEY", ""),
        "app_secret_key": os.getenv("APP_SECRET_KEY", "dev-secret"),
        "base_url": os.getenv("BASE_URL", "http://localhost:8000"),
        "database_path": os.getenv("DATABASE_PATH", config.get("database", {}).get("path", "data/vetflow.db")),
    }
    return config
