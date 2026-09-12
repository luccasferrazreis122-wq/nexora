import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    database: str = "data/nexora.sqlite3"
    model: str = "gpt-5.4-mini"
    user_daily_requests: int = 30
    global_daily_requests: int = 300
    user_minute_requests: int = 5
    global_minute_requests: int = 30
    access_seconds: int = 900
    refresh_seconds: int = 2592000
    max_output_tokens: int = 650

    @classmethod
    def from_env(cls):
        def positive(name, default):
            value = int(os.environ.get(name, default))
            if value <= 0:
                raise ValueError(f"{name} deve ser maior que zero")
            return value

        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            database=os.environ.get("NEXORA_DATABASE", "data/nexora.sqlite3"),
            model=os.environ.get("NEXORA_MODEL", "gpt-5.4-mini"),
            user_daily_requests=positive("NEXORA_USER_DAILY_REQUESTS", 30),
            global_daily_requests=positive("NEXORA_GLOBAL_DAILY_REQUESTS", 300),
            user_minute_requests=positive("NEXORA_USER_MINUTE_REQUESTS", 5),
            global_minute_requests=positive("NEXORA_GLOBAL_MINUTE_REQUESTS", 30),
        )
