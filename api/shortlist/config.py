from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./shortlist.db"
    public_base_url: str = "http://localhost:8000"
    web_origin: str = "http://localhost:3000"
    company_name: str = "Tallowmere"

    armoriq_api_key: str = ""
    armoriq_backend: str = "https://api.armoriq.ai"
    armoriq_proxy: str = "https://proxy.armoriq.ai"
    armoriq_agent_id: str = "shortlist-coordinator"
    agent_user_email: str = ""
    approver_email: str = ""
    mcp_shared_secret: str = ""
    token_validity_seconds: int = 900

    llm_base_url: str = "https://api.venice.ai/api/v1"
    llm_api_key: str = ""
    planner_model: str = ""
    executor_model: str = ""

    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    voice_webhook_secret: str = ""

    runs_per_workspace_per_hour: int = 40
    applications_per_workspace: int = 25
    global_runs_per_hour: int = 400
    global_workspaces_per_hour: int = 600
    admin_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
