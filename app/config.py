from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: Path = Path("data/nutrition.db")
    default_user_id: int = 1
    multi_user_enabled: bool = False
    api_version: str = "0.1.0"
    bearer_token: Optional[str] = None

    model_config = {"env_prefix": "NT_"}

    @model_validator(mode="after")
    def _multi_user_requires_a_token(self) -> "Settings":
        if self.multi_user_enabled and not self.bearer_token:
            raise ValueError(
                "NT_MULTI_USER_ENABLED requires NT_BEARER_TOKEN. Without a token "
                "every request is unauthenticated, so the combination would hand "
                "user provisioning and token rotation to anonymous callers."
            )
        return self


settings = Settings()
