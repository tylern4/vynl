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


settings = Settings()
