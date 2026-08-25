#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PLACEHOLDER = "__REPORT_DATA__"
FORBIDDEN_FIELDS = {"job_id", "node_list"}
FORBIDDEN_STRINGS = ("/home/", "runs/", "manifests/")


def assert_public_data(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in FORBIDDEN_FIELDS:
                raise ValueError(f"forbidden public field {path}.{key}")
            assert_public_data(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_public_data(item, f"{path}[{index}]")
    elif isinstance(value, str):
        assert_public_text(value, path)


def assert_public_text(text: str, source: str) -> None:
    folded = text.casefold()
    for forbidden in (*FORBIDDEN_FIELDS, *FORBIDDEN_STRINGS):
        if forbidden.casefold() in folded:
            raise ValueError(f"forbidden public token {forbidden!r} in {source}")


def render_payload(payload: str, template_path: Path, output_path: Path, source: str = "payload") -> Path:
    data = json.loads(payload)
    assert_public_data(data)
    assert_public_text(payload, source)
    template = template_path.read_text()
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"{template_path} must contain exactly one {PLACEHOLDER}")
    html = template.replace(PLACEHOLDER, payload)
    assert_public_text(html, str(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    print(f"wrote {output_path}")
    return output_path


def render_report(data_path: Path, template_path: Path, output_path: Path) -> Path:
    return render_payload(data_path.read_text(), template_path, output_path, str(data_path))


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <data.json> <template.html> <output.html>")
    render_report(*(Path(argument) for argument in sys.argv[1:]))


if __name__ == "__main__":
    main()
