"""Chinese documentation must not regress to untranslated Russian prose."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]


def _prose_lines(text: str) -> list[tuple[int, str]]:
    lines = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append((number, line))
    return lines


def test_prose_check_preserves_protocol_examples() -> None:
    text = '正文\n```json\n{"ru": "Название"}\n```\n~~~text\nПример\n~~~\n遗漏'
    assert _prose_lines(text) == [(1, "正文"), (8, "遗漏")]
    assert _prose_lines("正文\nРусский текст") == [(1, "正文"), (2, "Русский текст")]


def test_chinese_documentation_has_no_visible_russian() -> None:
    paths = [
        ROOT / name
        for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md", "AGENTS.md", "SECURITY.md")
    ]
    for directory in ("docs", "deploy/examples", "examples", ".github/ISSUE_TEMPLATE"):
        paths.extend((ROOT / directory).rglob("*.md"))
    violations = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        # Existing deep links and external source URLs retain their original spelling.
        text = re.sub(r'<a id="[^"]*"></a>', "", text)
        text = re.sub(r"\]\([^)]*\)", "]", text)
        text = re.sub(r"https?://[^\s<>]+", "", text)
        for line, content in _prose_lines(text):
            if re.search("[А-Яа-яЁё]", content):
                violations.append(f"{path.relative_to(ROOT)}:{line}: {content}")
    assert not violations, "\n".join(violations)


def test_openapi_titles_and_descriptions_are_chinese() -> None:
    import json

    from bot.app.web.openapi import generate_openapi

    document = generate_openapi()
    for methods in document["paths"].values():
        for operation in methods.values():
            assert re.search("[\u4e00-\u9fff]", operation["summary"]), operation["operationId"]
            assert all(re.search("[\u4e00-\u9fff]", tag) for tag in operation["tags"])

    def descriptions(value: object) -> None:
        if isinstance(value, dict):
            record = cast(dict[str, object], value)
            text = record.get("description")
            if isinstance(text, str):
                assert re.search("[\u4e00-\u9fff]", text), text
            for item in record.values():
                descriptions(item)
        elif isinstance(value, list):
            for item in cast(list[object], value):
                descriptions(item)

    descriptions(document)
    catalog = json.loads((ROOT / "backend/bot/app/web/openapi.zh-hans.json").read_text())
    assert set(catalog["operations"]) == {
        operation["operationId"]
        for methods in document["paths"].values()
        for operation in methods.values()
    }
