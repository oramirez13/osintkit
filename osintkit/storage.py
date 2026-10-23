"""Result storage and export (JSONL and CSV)."""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _flatten(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        elif isinstance(value, (list, tuple)):
            flat[name] = json.dumps(value, ensure_ascii=False)
        else:
            flat[name] = value
    return flat


class Recorder:
    """Accumulates records and allows exporting to multiple formats."""

    def __init__(self, output_dir: str = "output", prefix: str = "run") -> None:
        self.output_dir = ensure_dir(output_dir)
        self.records: list[dict[str, Any]] = []
        self.stamp = timestamp()
        self.prefix = f"{prefix}_{self.stamp}"

    def add(self, **fields: Any) -> dict[str, Any]:
        fields.setdefault("captured_at", datetime.now(timezone.utc).isoformat())
        self.records.append(fields)
        return fields

    def extend(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            self.add(**row)

    def _path(self, ext: str) -> str:
        return os.path.join(self.output_dir, f"{self.prefix}.{ext}")

    def save_jsonl(self) -> str:
        path = self._path("jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def save_json(self) -> str:
        path = self._path("json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.records, handle, ensure_ascii=False, indent=2)
        return path

    def save_csv(self) -> str | None:
        if not self.records:
            return None
        rows = [_flatten(record) for record in self.records]
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        path = self._path("csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _sanitize_csv_cell(row.get(k, "")) for k in fieldnames})
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return path

    def save_all(self, formats: Iterable[str] = ("jsonl", "csv")) -> list[str]:
        paths: list[str] = []
        for fmt in formats:
            if fmt == "jsonl":
                paths.append(self.save_jsonl())
            elif fmt == "json":
                paths.append(self.save_json())
            elif fmt == "csv":
                csv_path = self.save_csv()
                if csv_path:
                    paths.append(csv_path)
        return paths
