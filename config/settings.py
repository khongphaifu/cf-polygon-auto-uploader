import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any
import yaml


@dataclass
class PolygonConfig:
    api_key: str = ""
    api_secret: str = ""
    api_url: str = "https://polygon.codeforces.com/api/"


@dataclass
class AIConfig:
    provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_backup_keys: list = field(default_factory=list)
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    model_name: str = "gemini-3.5-flash-lite"


@dataclass
class GenerationConfig:
    num_tests: int = 20
    include_samples_in_statements: bool = True
    default_time_limit_ms: int = 1000
    default_memory_limit_mb: int = 256
    auto_grant_access_to_codeforces: bool = True
    auto_package: bool = True


@dataclass
class ExportConfig:
    excel_file_path: str = "problems_summary.xlsx"


@dataclass
class AppConfig:
    polygon: PolygonConfig = field(default_factory=PolygonConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    if config_path is None:
        config_path = get_project_root() / "config" / "config.yaml"
    
    if not config_path.exists():
        # Fallback to environment variables
        return AppConfig(
            polygon=PolygonConfig(
                api_key=os.getenv("POLYGON_API_KEY", ""),
                api_secret=os.getenv("POLYGON_API_SECRET", ""),
                api_url=os.getenv("POLYGON_API_URL", "https://polygon.codeforces.com/api/"),
            ),
            ai=AIConfig(
                provider=os.getenv("AI_PROVIDER", "gemini"),
                gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
                model_name=os.getenv("AI_MODEL_NAME", "gemini-2.5-flash"),
            ),
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    polygon_data = data.get("polygon", {})
    ai_data = data.get("ai", {})
    gen_data = data.get("generation", {})
    export_data = data.get("export", {})

    return AppConfig(
        polygon=PolygonConfig(**polygon_data),
        ai=AIConfig(**ai_data),
        generation=GenerationConfig(**gen_data),
        export=ExportConfig(**export_data),
    )
