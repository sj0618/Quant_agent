from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.db.pdf_temp_repository import (
    PdfTempFileRecord,
    PdfTempRepository,
    new_pdf_id,
    utc_now_iso,
)
from app.services.pdf_temp_seed_registry import EnvPdfTempSeedProvider, PdfTempSeed, PdfTempSeedProvider
from app.services.pdf_text_extractor import extract_pdf_text


@dataclass(frozen=True, slots=True)
class StagedPdf:
    path: Path
    original_filename: str
    size_bytes: int


class PdfTempIngestFailure(RuntimeError):
    def __init__(self, reason: str, original_filename: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.original_filename = original_filename


class PdfTempIngestService:
    def __init__(self, settings: Settings, repository: PdfTempRepository, seed_provider: PdfTempSeedProvider | None = None):
        self.settings = settings
        self.repository = repository
        self.seed_provider = seed_provider or EnvPdfTempSeedProvider.from_settings(settings)

    async def ingest(self, seed_ids: list[str] | None, *, force: bool = False) -> list[PdfTempFileRecord]:
        seeds = await self._select_seeds(seed_ids)
        results: list[PdfTempFileRecord] = []
        for seed in seeds:
            results.append(await self.ingest_seed(seed, force=force))
        return results

    async def ingest_seed(self, seed: PdfTempSeed, *, force: bool = False) -> PdfTempFileRecord:
        if not force:
            existing = await self.repository.find_latest_by_seed(seed.seed_id)
            if existing is not None and existing.status != "failed":
                return existing

        staged: StagedPdf | None = None
        try:
            staged = await self._stage_seed(seed)
            self._validate_pdf_signature(staged.path)
            file_hash = _sha256_file(staged.path)
            if seed.expected_sha256 and seed.expected_sha256.lower() != file_hash.lower():
                raise PdfTempIngestFailure("PDF hash did not match expected seed hash", staged.original_filename)

            canonical = await self.repository.find_canonical_by_hash(file_hash)
            if canonical is not None:
                _cleanup(staged.path)
                return await self._save_duplicate(seed, canonical, staged.original_filename, staged.size_bytes)

            pdf_id = new_pdf_id()
            artifact_key = f"{file_hash}.pdf"
            final_path = self._storage_root() / artifact_key
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if final_path.exists():
                _cleanup(staged.path)
            else:
                os.replace(staged.path, final_path)

            extraction = extract_pdf_text(pdf_id, final_path, self.settings.pdf_temp_min_text_chars)
            now = utc_now_iso()
            record = PdfTempFileRecord(
                pdf_id=pdf_id,
                seed_id=seed.seed_id,
                source_type=seed.source_type,
                safe_source_label=seed.label,
                stored_artifact_key=artifact_key,
                original_filename=staged.original_filename,
                file_hash=file_hash,
                size_bytes=staged.size_bytes,
                page_count=extraction.page_count,
                status=extraction.status,  # type: ignore[arg-type]
                failure_reason=extraction.failure_reason,
                canonical_pdf_id=None,
                created_at=now,
                updated_at=now,
                **_seed_metadata(seed),
            )
            return await self.repository.save_file(record, extraction.pages)
        except PdfTempIngestFailure as exc:
            if staged is not None:
                _cleanup(staged.path)
            return await self._save_failed(seed, exc.reason, exc.original_filename)
        except AppError as exc:
            if staged is not None:
                _cleanup(staged.path)
            reason = str(exc.message)
            return await self._save_failed(seed, reason, staged.original_filename if staged else None)
        except Exception as exc:  # noqa: BLE001
            if staged is not None:
                _cleanup(staged.path)
            return await self._save_failed(seed, f"PDF ingest failed: {type(exc).__name__}", staged.original_filename if staged else None)

    async def _select_seeds(self, seed_ids: list[str] | None) -> list[PdfTempSeed]:
        if seed_ids is None:
            seeds = await self.seed_provider.enabled()
        else:
            seeds = [await self.seed_provider.require(seed_id) for seed_id in seed_ids]
        if len(seeds) > self.settings.pdf_temp_max_seed_batch_size:
            raise AppError(
                status_code=400,
                component="pdf_temp",
                code="too_many_pdf_seeds",
                message="PDF seed batch exceeds configured limit",
                details={"limit": self.settings.pdf_temp_max_seed_batch_size},
            )
        return seeds

    async def _stage_seed(self, seed: PdfTempSeed) -> StagedPdf:
        if seed.source_type == "file":
            return self._stage_file_seed(seed)
        return await self._stage_url_seed(seed)

    def _stage_file_seed(self, seed: PdfTempSeed) -> StagedPdf:
        source = self._resolve_seed_file(seed)
        original_filename = source.name
        if not source.exists() or not source.is_file():
            raise PdfTempIngestFailure("PDF seed file is unavailable", original_filename)
        size_bytes = source.stat().st_size
        if size_bytes > self.settings.pdf_temp_max_bytes:
            raise PdfTempIngestFailure("PDF seed file exceeds maximum size", original_filename)
        staged_path = self._staging_path(seed, original_filename)
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, staged_path)
        return StagedPdf(path=staged_path, original_filename=original_filename, size_bytes=size_bytes)

    async def _stage_url_seed(self, seed: PdfTempSeed) -> StagedPdf:
        url = seed.source_url or ""
        self._validate_seed_url(url)
        original_filename = _filename_from_url(url)
        staged_path = self._staging_path(seed, original_filename)
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            size_bytes = await self._download_url_to_staging(url, staged_path)
        except PdfTempIngestFailure:
            _cleanup(staged_path)
            raise
        return StagedPdf(path=staged_path, original_filename=original_filename, size_bytes=size_bytes)

    async def _download_url_to_staging(self, url: str, staged_path: Path) -> int:
        current_url = url
        redirects_followed = 0
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                headers={"User-Agent": self.settings.pdf_temp_http_user_agent},
                timeout=self.settings.pdf_temp_url_timeout_seconds,
            ) as client:
                while True:
                    self._validate_seed_url(current_url)
                    async with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            if redirects_followed >= self.settings.pdf_temp_url_max_redirects:
                                raise PdfTempIngestFailure("PDF seed URL exceeded redirect limit", _filename_from_url(url))
                            location = response.headers.get("location")
                            if not location:
                                raise PdfTempIngestFailure("PDF seed URL redirect was missing location", _filename_from_url(url))
                            next_url = urljoin(str(response.url), location)
                            self._validate_seed_url(next_url)
                            current_url = next_url
                            redirects_followed += 1
                            continue

                        response.raise_for_status()
                        size_bytes = 0
                        with staged_path.open("wb") as handle:
                            async for chunk in response.aiter_bytes():
                                size_bytes += len(chunk)
                                if size_bytes > self.settings.pdf_temp_max_bytes:
                                    raise PdfTempIngestFailure(
                                        "PDF seed URL payload exceeds maximum size",
                                        _filename_from_url(url),
                                    )
                                handle.write(chunk)
                        return size_bytes
        except PdfTempIngestFailure:
            raise
        except httpx.TimeoutException as exc:
            raise PdfTempIngestFailure("PDF seed URL timed out", _filename_from_url(url)) from exc
        except httpx.HTTPError as exc:
            raise PdfTempIngestFailure(f"PDF seed URL request failed: {type(exc).__name__}", _filename_from_url(url)) from exc

    def _resolve_seed_file(self, seed: PdfTempSeed) -> Path:
        base = Path(self.settings.pdf_temp_seed_dir).resolve(strict=False)
        raw = Path(seed.source_path or "")
        candidate = raw if raw.is_absolute() else base / raw
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise PdfTempIngestFailure("PDF seed file escaped the configured seed directory", candidate.name) from exc
        return resolved

    def _validate_seed_url(self, url: str) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        allowed_hosts = {item.lower() for item in self.settings.pdf_temp_allowed_hosts}
        if parsed.scheme not in {"http", "https"} or not host or host not in allowed_hosts:
            raise PdfTempIngestFailure("PDF seed URL host is not allowed", _filename_from_url(url))

    def _validate_pdf_signature(self, path: Path) -> None:
        with path.open("rb") as handle:
            header = handle.read(5)
        if header != b"%PDF-":
            raise PdfTempIngestFailure("PDF payload signature is invalid", path.name)

    def _storage_root(self) -> Path:
        return Path(self.settings.pdf_temp_storage_dir)

    def _staging_path(self, seed: PdfTempSeed, original_filename: str) -> Path:
        safe_name = Path(original_filename).name or f"{seed.seed_id}.pdf"
        return self._storage_root() / "_staging" / f"{seed.seed_id}-{new_pdf_id()}-{safe_name}"

    async def _save_duplicate(
        self,
        seed: PdfTempSeed,
        canonical: PdfTempFileRecord,
        original_filename: str | None,
        size_bytes: int,
    ) -> PdfTempFileRecord:
        now = utc_now_iso()
        record = PdfTempFileRecord(
            pdf_id=new_pdf_id(),
            seed_id=seed.seed_id,
            source_type=seed.source_type,
            safe_source_label=seed.label,
            stored_artifact_key=canonical.stored_artifact_key,
            original_filename=original_filename,
            file_hash=canonical.file_hash,
            size_bytes=size_bytes,
            page_count=canonical.page_count,
            status="duplicate",
            failure_reason=None,
            canonical_pdf_id=canonical.pdf_id,
            created_at=now,
            updated_at=now,
            **_seed_metadata(seed),
        )
        return await self.repository.save_file(record, [])

    async def _save_failed(self, seed: PdfTempSeed, reason: str, original_filename: str | None) -> PdfTempFileRecord:
        now = utc_now_iso()
        record = PdfTempFileRecord(
            pdf_id=new_pdf_id(),
            seed_id=seed.seed_id,
            source_type=seed.source_type,
            safe_source_label=seed.label,
            stored_artifact_key=None,
            original_filename=original_filename,
            file_hash=None,
            size_bytes=0,
            page_count=0,
            status="failed",
            failure_reason=reason,
            canonical_pdf_id=None,
            created_at=now,
            updated_at=now,
            **_seed_metadata(seed),
        )
        return await self.repository.save_file(record, [])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _filename_from_url(url: str) -> str:
    name = Path(urlsplit(url).path).name
    return name if name.lower().endswith(".pdf") else "seed.pdf"


def _seed_metadata(seed: PdfTempSeed) -> dict[str, str | None]:
    return {
        "report_idx": seed.report_idx,
        "report_title": seed.title,
        "company_name": seed.company,
        "ticker": seed.ticker,
        "broker": seed.broker,
        "report_date": seed.report_date,
    }
