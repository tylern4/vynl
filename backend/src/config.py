from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vynl:vynl@localhost:5432/vynl"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days
    invite_code: str = "change-me"
    musicbrainz_contact: str = "you@example.com"
    covers_dir: str = "covers"
    # Discogs personal access token (account → Developers → Generate token).
    # Blank = the Discogs provider is disabled (issue #12).
    discogs_token: str = ""
    # iTunes storefronts queried per search, comma-separated; order = query
    # order. Override for e.g. "US,JP,GB,DE,FR" (issue #12).
    itunes_countries: str = "US,JP,GB"


settings = Settings()
