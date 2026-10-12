"""全局配置：全部来自环境变量，便于在不同环境（本机/执行机）复用同一份代码。"""
import os
from dataclasses import dataclass, field


def _csv(name: str) -> list:
    return [s.strip() for s in os.getenv(name, "").split(",") if s.strip()]


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///dlmu.db")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    output_dir: str = os.getenv("OUTPUT_DIR", "./outputs")
    card_font: str = os.getenv("CARD_FONT", "")
    default_pool: list = field(default_factory=lambda: _csv("DEFAULT_POOL"))

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)


settings = Settings()
