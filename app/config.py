from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bta:bta_secret@postgres:5432/bug_tracking"

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # GitHub
    GITHUB_TOKEN: str
    GITHUB_WEBHOOK_SECRET: str
    GITHUB_REPO: str

    @field_validator("GITHUB_REPO")
    @classmethod
    def strip_git_suffix(cls, v: str) -> str:
        return v.removesuffix(".git")

    # Jira
    JIRA_BASE_URL: str
    JIRA_EMAIL: str
    JIRA_API_TOKEN: str
    JIRA_PROJECT_KEY: str = "BUG"

    # TestRail
    TESTRAIL_BASE_URL: str = ""
    TESTRAIL_EMAIL: str = ""
    TESTRAIL_API_KEY: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()
