import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    database: str = field(default="data/nexora.sqlite3", repr=False)
    model: str = "gpt-5.4-mini"
    user_daily_requests: int = 30
    global_daily_requests: int = 300
    user_minute_requests: int = 5
    global_minute_requests: int = 30
    access_seconds: int = 900
    refresh_seconds: int = 2592000
    max_output_tokens: int = 650
    trials_enabled: bool = True
    trial_daily_registrations: int = 20
    trial_peer_daily_registrations: int = 3

    @classmethod
    def from_env(cls):
        def positive(name, default):
            value = int(os.environ.get(name, default))
            if value <= 0:
                raise ValueError(f"{name} deve ser maior que zero")
            return value

        database = os.environ.get("DATABASE_URL") or os.environ.get("NEXORA_DATABASE", "data/nexora.sqlite3")
        if os.environ.get("NEXORA_REQUIRE_POSTGRES") == "1" and not database.startswith(("postgres://", "postgresql://")):
            raise ValueError("Configure DATABASE_URL com o banco PostgreSQL externo")
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            database=database,
            model=os.environ.get("NEXORA_MODEL", "gpt-5.4-mini"),
            user_daily_requests=positive("NEXORA_USER_DAILY_REQUESTS", 30),
            global_daily_requests=positive("NEXORA_GLOBAL_DAILY_REQUESTS", 300),
            user_minute_requests=positive("NEXORA_USER_MINUTE_REQUESTS", 5),
            global_minute_requests=positive("NEXORA_GLOBAL_MINUTE_REQUESTS", 30),
            trials_enabled=os.environ.get("NEXORA_TRIALS_ENABLED", "1") == "1",
            trial_daily_registrations=positive("NEXORA_TRIAL_DAILY_REGISTRATIONS", 20),
            trial_peer_daily_registrations=positive("NEXORA_TRIAL_PEER_DAILY_REGISTRATIONS", 3),
        )
