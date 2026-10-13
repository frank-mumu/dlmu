"""全局配置：来自环境变量；若存在 .env 会先加载（不覆盖已存在的环境变量）。"""
import os
from dataclasses import dataclass, field


def _load_dotenv(path: str = ".env") -> None:
    """极简 .env 加载（不引入 python-dotenv 依赖）；不覆盖已有环境变量。"""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv()


def _csv(name: str) -> list:
    return [s.strip() for s in os.getenv(name, "").split(",") if s.strip()]


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///dlmu.db")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    search_api_url: str = os.getenv("SEARCH_API_URL", "")
    search_api_key: str = os.getenv("SEARCH_API_KEY", "")
    output_dir: str = os.getenv("OUTPUT_DIR", "./outputs")
    card_font: str = os.getenv("CARD_FONT", "")
    default_pool: list = field(default_factory=lambda: _csv("DEFAULT_POOL"))

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)


settings = Settings()
