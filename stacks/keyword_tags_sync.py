"""Copy config/keyword_tags.json into lambda/analysis/ for the Analysis Lambda asset."""

from __future__ import annotations

import shutil
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _ROOT / "config" / "keyword_tags.json"
ANALYSIS_TARGET = _ROOT / "lambda" / "analysis" / "keyword_tags.json"


def sync_keyword_tags() -> None:
    """Ensure the analysis Lambda directory has keyword_tags.json from config/."""
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"Missing {CONFIG_PATH}. Create it as a JSON array of keyword strings."
        )
    ANALYSIS_TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONFIG_PATH, ANALYSIS_TARGET)
