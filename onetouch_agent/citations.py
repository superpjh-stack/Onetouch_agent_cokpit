from __future__ import annotations

from typing import Any


def _value(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def extract_sources(response: Any) -> list[str]:
    sources: list[str] = []
    for item in _value(response, "output", []) or []:
        if _value(item, "type") != "message":
            continue
        for content in _value(item, "content", []) or []:
            for annotation in _value(content, "annotations", []) or []:
                if _value(annotation, "type") == "file_citation":
                    filename = _value(annotation, "filename")
                    if filename and filename not in sources:
                        sources.append(filename)
    return sources


def extract_evidence(response: Any, limit: int = 5) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in _value(response, "output", []) or []:
        if _value(item, "type") != "file_search_call":
            continue
        for result in (_value(item, "results") or _value(item, "search_results") or []):
            evidence.append({"filename": _value(result, "filename", "알 수 없는 문서"), "score": _value(result, "score"), "text": _value(result, "text", "")})
            if len(evidence) >= limit:
                return evidence
    return evidence
