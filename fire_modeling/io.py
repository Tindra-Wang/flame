"""Artifact serialization and boundary checks shared by adapters."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolve_artifact(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Artifact escapes run directory: {relative}")
    return target


def new_directory(path: str | Path) -> Path:
    target = Path(path).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"Output is not empty; choose a new directory: {target}")
    target.mkdir(parents=True, exist_ok=True)
    return target
