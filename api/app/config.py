from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from RT_* environment variables,
    injected by Coolify in production and .env locally."""

    model_config = SettingsConfigDict(env_prefix="RT_", env_file=".env", extra="ignore")

    app_name: str = "Roundtable"
    env: str = "prod"  # dev | test | prod
    public_base_url: str = "http://localhost:8080"

    # Signing key for session cookies and the pre-auth cookie. Must be set in prod.
    secret_key: str = "dev-only-not-a-secret"

    database_url: str = "postgresql+asyncpg://roundtable:roundtable@localhost:5433/roundtable"
    redis_url: str = "redis://localhost:6380/0"

    oidc_issuer: str = "https://id.example.com"
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    # Local development sign-in that skips the identity server entirely.
    # Refused unless env is dev; the app refuses to start if both are set.
    dev_login: bool = False

    # Comma-separated. Matched case-insensitively on first login to grant the admin role.
    bootstrap_admin_usernames: str = ""
    bootstrap_admin_emails: str = ""

    cookie_secure: bool = True
    session_ttl_days: int = 30
    preauth_ttl_seconds: int = 600

    # External catalog APIs. Keys are provided by the admin; the app runs
    # without them but catalog pages will show a setup notice.
    tmdb_api_key: str = ""
    # TMDB v4 read access token. Preferred when present: sent as a bearer
    # header instead of the v3 api_key query parameter.
    tmdb_access_token: str = ""
    omdb_api_key: str = ""
    omdb_daily_budget: int = 900  # free tier is 1000/day, keep headroom
    # The parents guide reads an unofficial IMDb endpoint that their terms
    # do not permit being read this way. Off by default so nobody enables it
    # by accident: turning it on is the operator's decision about their own
    # instance and their own risk. With it off the advisory still works and
    # falls back to the generated estimate, which the response labels.
    imdb_guide_enabled: bool = False
    # Availability country used when a profile has no country set yet.
    default_country: str = "US"

    # Uploads (avatars, import files). Overridden to the /data volume in
    # production compose; a local folder in development.
    data_dir: str = "./data"
    avatar_max_bytes: int = 5 * 1024 * 1024

    # Push notifications. Empty ntfy_url disables push; the inbox always works.
    ntfy_url: str = ""

    # Email, through Resend. Absent means email is simply off, which is the
    # default and not an error.
    resend_api_key: str | None = None
    # Must be a domain verified with Resend before anything will send.
    resend_from: str | None = None
    ntfy_topic_prefix: str = "roundtable-"

    @property
    def sync_database_url(self) -> str:
        """Alembic runs on a synchronous engine."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def oidc_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/auth/callback"

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.tmdb_api_key or self.tmdb_access_token)

    @property
    def dev_login_enabled(self) -> bool:
        """Two independent switches must agree, so a stray RT_DEV_LOGIN in a
        production environment does nothing."""
        return self.dev_login and self.env == "dev"

    @property
    def admin_usernames(self) -> set[str]:
        return {u.strip().lower() for u in self.bootstrap_admin_usernames.split(",") if u.strip()}

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.bootstrap_admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
