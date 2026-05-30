from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.retrieval.search import DEFAULT_CORPUS_DIR, load_markdown_corpus


L1_REQUIRED_FIELDS = (
    "definition:",
    "formula:",
    "recommended_thresholds:",
    "sources:",
    "bull_case:",
    "bear_case:",
    "examples:",
)
L2_REQUIRED_FIELDS = (
    "indicator_name:",
    "formula:",
    "category:",
    "available_db_source:",
)


class CatalogValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    l1_count: int = Field(ge=0)
    l2_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_catalog(corpus_dir: Path | None = None) -> CatalogValidationResult:
    root = corpus_dir or DEFAULT_CORPUS_DIR
    documents = load_markdown_corpus(root)
    errors: list[str] = []
    l1_count = 0
    l2_count = 0
    for document in documents:
        if document.level == "L1":
            entries = _split_catalog_entries(document.body, prefix="strategy_id:")
            if entries:
                l1_count += len(entries)
                errors.extend(_missing_fields(document.document_id, entries, L1_REQUIRED_FIELDS))
            else:
                l1_count += 1
        else:
            entries = _split_catalog_entries(document.body, prefix="indicator_name:")
            if entries:
                l2_count += len(entries)
                errors.extend(_missing_fields(document.document_id, entries, L2_REQUIRED_FIELDS))
            else:
                l2_count += 1
    if l1_count < 50:
        errors.append(f"L1 catalog has {l1_count} entries; expected at least 50.")
    if l2_count < 150:
        errors.append(f"L2 catalog has {l2_count} entries; expected at least 150.")
    return CatalogValidationResult(l1_count=l1_count, l2_count=l2_count, errors=errors)


def _split_catalog_entries(body: str, *, prefix: str) -> list[str]:
    lines = body.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip().startswith(prefix)]
    if not starts:
        return []
    entries: list[str] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        entries.append("\n".join(lines[start:end]))
    return entries


def _missing_fields(
    document_id: str,
    entries: list[str],
    required_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    for index, entry in enumerate(entries, start=1):
        errors.extend(_missing_single_fields(f"{document_id}#{index}", entry, required_fields))
    return errors


def _missing_single_fields(
    entry_id: str,
    body: str,
    required_fields: tuple[str, ...],
) -> list[str]:
    lowered = body.lower()
    return [f"{entry_id} missing {field}" for field in required_fields if field not in lowered]
