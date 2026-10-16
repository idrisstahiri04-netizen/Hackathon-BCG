from datetime import date
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent                      # announcements/
CACHE = ROOT / ".cache"                # raw downloads + extracted text (git-ignored)
OUTPUT = ROOT / "output"               # final results (committed)


def load_sources(path: Path = PKG / "sources.yaml") -> tuple[dict, list[dict]]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    d = cfg.get("defaults", {})
    d["date_from"] = str(d.get("date_from") or "2021-10-16")
    d["date_to"] = str(d.get("date_to") or date.today().isoformat())
    return d, cfg["sources"]


def load_keywords(path: Path = PKG / "keywords.yaml") -> tuple[list[str], dict[str, list[str]]]:
    """(broad search terms, full tag list by group)."""
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    tags = {g: [str(k) for k in ks] for g, ks in cfg["tags"].items()}
    return [str(t) for t in cfg["search_terms"]], tags
