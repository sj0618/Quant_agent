from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from app.core.config import Settings
from app.core.errors import AppError
from app.db.pdf_temp_repository import HankyungConsensusPdfTempSeedRecord, PdfTempDbRepository

SeedSourceType = Literal["url", "file"]
_SEED_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
_REPORT_IDX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
_HANKYUNG_SEED_ID_RE = re.compile(r"^hankyung-(?P<report_idx>\d+)$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class PdfTempSeed:
    seed_id: str
    source_type: SeedSourceType
    label: str
    enabled: bool
    source_url: str | None = None
    source_path: str | None = None
    expected_sha256: str | None = None
    report_idx: str | None = None
    title: str | None = None
    company: str | None = None
    ticker: str | None = None
    broker: str | None = None
    report_date: str | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "seedId": self.seed_id,
            "sourceType": self.source_type,
            "label": self.label,
            "enabled": self.enabled,
            "reportIdx": self.report_idx,
            "title": self.title,
            "company": self.company,
            "ticker": self.ticker,
            "broker": self.broker,
            "reportDate": self.report_date,
        }


class PdfTempSeedRegistry:
    def __init__(self, seeds: list[PdfTempSeed]):
        self._seeds = seeds
        self._by_id = {seed.seed_id: seed for seed in seeds}
        if len(self._by_id) != len(seeds):
            raise AppError(
                status_code=503,
                component="pdf_temp",
                code="invalid_seed_registry",
                message="PDF seed registry contains duplicate seed IDs",
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "PdfTempSeedRegistry":
        try:
            raw = json.loads(settings.pdf_temp_seed_registry_json or "[]")
        except json.JSONDecodeError as exc:
            raise AppError(
                status_code=503,
                component="pdf_temp",
                code="invalid_seed_registry",
                message="PDF seed registry JSON is invalid",
                details={"error": exc.msg},
            ) from exc
        if not isinstance(raw, list):
            raise AppError(
                status_code=503,
                component="pdf_temp",
                code="invalid_seed_registry",
                message="PDF seed registry must be a list",
            )
        return cls([_seed_from_mapping(item) for item in raw])

    def list(self) -> list[PdfTempSeed]:
        return list(self._seeds)

    def enabled(self) -> list[PdfTempSeed]:
        return [seed for seed in self._seeds if seed.enabled]

    def require(self, seed_id: str) -> PdfTempSeed:
        seed = self._by_id.get(seed_id)
        if seed is None:
            raise AppError(
                status_code=400,
                component="pdf_temp",
                code="unknown_seed_id",
                message="PDF seed ID is not registered",
                details={"seed_id": seed_id},
            )
        if not seed.enabled:
            raise AppError(
                status_code=400,
                component="pdf_temp",
                code="disabled_seed_id",
                message="PDF seed ID is disabled",
                details={"seed_id": seed_id},
            )
        return seed


class PdfTempSeedProvider(Protocol):
    async def list(self) -> list[PdfTempSeed]: ...

    async def enabled(self) -> list[PdfTempSeed]: ...

    async def require(self, seed_id: str) -> PdfTempSeed: ...


class EnvPdfTempSeedProvider:
    def __init__(self, registry: PdfTempSeedRegistry):
        self.registry = registry

    @classmethod
    def from_settings(cls, settings: Settings) -> "EnvPdfTempSeedProvider":
        return cls(PdfTempSeedRegistry.from_settings(settings))

    async def list(self) -> list[PdfTempSeed]:
        return self.registry.list()

    async def enabled(self) -> list[PdfTempSeed]:
        return self.registry.enabled()

    async def require(self, seed_id: str) -> PdfTempSeed:
        return self.registry.require(seed_id)


class DbPdfTempSeedProvider:
    def __init__(self, repository: PdfTempDbRepository):
        self.repository = repository

    async def list(self) -> list[PdfTempSeed]:
        return [_seed_from_db_record(record) for record in await self.repository.list_crawler_seeds(status=None)]

    async def enabled(self) -> list[PdfTempSeed]:
        return [seed for seed in await self.list() if seed.enabled]

    async def require(self, seed_id: str) -> PdfTempSeed:
        record = await self.repository.get_crawler_seed(seed_id)
        if record is None:
            raise AppError(
                status_code=400,
                component="pdf_temp",
                code="unknown_seed_id",
                message="PDF seed ID is not registered",
                details={"seed_id": seed_id},
            )
        if record.status != "active":
            raise AppError(
                status_code=400,
                component="pdf_temp",
                code="disabled_seed_id",
                message="PDF seed ID is disabled",
                details={"seed_id": seed_id},
            )
        return _seed_from_db_record(record)


class CombinedPdfTempSeedProvider:
    def __init__(self, env_provider: PdfTempSeedProvider, db_provider: PdfTempSeedProvider | None = None):
        self.env_provider = env_provider
        self.db_provider = db_provider

    async def list(self) -> list[PdfTempSeed]:
        env_seeds = await self.env_provider.list()
        if self.db_provider is None:
            return env_seeds
        db_seeds = await self.db_provider.list()
        self._reject_collisions(env_seeds, db_seeds)
        return [*env_seeds, *db_seeds]

    async def enabled(self) -> list[PdfTempSeed]:
        return [seed for seed in await self.list() if seed.enabled]

    async def require(self, seed_id: str) -> PdfTempSeed:
        env_contains_seed_id = False
        if self.db_provider is not None and seed_id.startswith("hankyung-crawl-"):
            env_contains_seed_id = any(seed.seed_id == seed_id for seed in await self.env_provider.list())

        env_seed: PdfTempSeed | None = None
        env_error: AppError | None = None
        try:
            env_seed = await self.env_provider.require(seed_id)
        except AppError as exc:
            env_error = exc

        db_seed: PdfTempSeed | None = None
        db_error: AppError | None = None
        if self.db_provider is not None and (env_seed is None or seed_id.startswith("hankyung-crawl-")):
            try:
                db_seed = await self.db_provider.require(seed_id)
            except AppError as exc:
                db_error = exc

        if (env_seed is not None or env_contains_seed_id) and db_seed is not None:
            self._raise_collision(seed_id)
        if env_seed is not None:
            return env_seed
        if db_seed is not None:
            return db_seed
        if db_error is not None and db_error.code != "unknown_seed_id":
            raise db_error
        if env_error is not None:
            raise env_error
        raise AppError(
            status_code=400,
            component="pdf_temp",
            code="unknown_seed_id",
            message="PDF seed ID is not registered",
            details={"seed_id": seed_id},
        )

    def _reject_collisions(self, env_seeds: list[PdfTempSeed], db_seeds: list[PdfTempSeed]) -> None:
        env_ids = {seed.seed_id for seed in env_seeds}
        collisions = sorted(env_ids.intersection(seed.seed_id for seed in db_seeds))
        if collisions:
            self._raise_collision(collisions[0])

    def _raise_collision(self, seed_id: str) -> None:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="seed_provider_collision",
            message="PDF seed providers contain duplicate seed IDs",
            details={"seed_id": seed_id},
        )


def _seed_from_mapping(item: Any) -> PdfTempSeed:
    if not isinstance(item, dict):
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="PDF seed registry entries must be objects",
        )
    seed_id = _required_str(item, "seed_id")
    if _SEED_ID_RE.match(seed_id) is None:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="PDF seed ID must be a simple token",
        )
    source_type = _required_str(item, "source_type")
    if source_type not in {"url", "file"}:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="PDF seed source_type must be url or file",
        )
    label = _required_str(item, "label")
    enabled = bool(item.get("enabled", True))
    source_url = _optional_str(item, "source_url")
    source_path = _optional_str(item, "source_path")
    expected_sha256 = _optional_str(item, "expected_sha256")
    report_idx = _report_idx(item, seed_id)
    report_date = _optional_iso_date(item, "report_date")
    if source_type == "url" and not source_url:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="URL PDF seeds require source_url",
        )
    if source_type == "file" and not source_path:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="File PDF seeds require source_path",
        )
    return PdfTempSeed(
        seed_id=seed_id,
        source_type=source_type,  # type: ignore[arg-type]
        label=label,
        enabled=enabled,
        source_url=source_url,
        source_path=source_path,
        expected_sha256=expected_sha256,
        report_idx=report_idx,
        title=_optional_metadata_str(item, "title"),
        company=_optional_metadata_str(item, "company"),
        ticker=_optional_metadata_str(item, "ticker"),
        broker=_optional_metadata_str(item, "broker"),
        report_date=report_date,
    )


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message=f"PDF seed registry entry requires {key}",
        )
    return value.strip()


def _optional_str(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _report_idx(item: dict[str, Any], seed_id: str) -> str | None:
    explicit = _optional_metadata_str(item, "report_idx")
    value = explicit
    if value is None:
        match = _HANKYUNG_SEED_ID_RE.match(seed_id)
        value = match.group("report_idx") if match else None
    if value is None:
        return None
    if _REPORT_IDX_RE.match(value) is None:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message="PDF seed report_idx must be a simple token",
        )
    return value


def _optional_metadata_str(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message=f"PDF seed registry entry has invalid {key}",
        )
    normalized = value.strip()
    return normalized or None


def _optional_iso_date(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message=f"PDF seed registry entry has invalid {key}",
        )
    normalized = value.strip()
    if _ISO_DATE_RE.match(normalized) is None:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message=f"PDF seed registry entry has invalid {key}",
        )
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_seed_registry",
            message=f"PDF seed registry entry has invalid {key}",
        ) from exc
    return normalized


def _seed_from_db_record(record: HankyungConsensusPdfTempSeedRecord) -> PdfTempSeed:
    return PdfTempSeed(
        seed_id=record.seed_id,
        source_type="url",
        label=record.report_title or record.company_name or f"Hankyung report {record.report_idx}",
        enabled=record.status == "active",
        source_url=record.pdf_url,
        report_idx=record.report_idx,
        title=record.report_title,
        company=record.company_name,
        ticker=record.ticker,
        broker=record.broker,
        report_date=record.report_date if isinstance(record.report_date, str) else record.report_date.isoformat() if record.report_date else None,
    )
