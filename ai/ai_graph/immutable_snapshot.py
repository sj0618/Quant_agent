"""Immutable, hash-addressed snapshots for PIT and indicator inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SnapshotKind = Literal["pit_universe", "delisting", "indicator_input"]
SNAPSHOT_KINDS: tuple[SnapshotKind, ...] = (
    "pit_universe",
    "delisting",
    "indicator_input",
)
SNAPSHOT_HASH_PATTERN = r"^[0-9a-f]{64}$"
SNAPSHOT_HASH_LENGTH = 64
SNAPSHOT_SCHEMA_VERSION = "immutable-input-snapshot.v1"


class ImmutableSnapshot(BaseModel):
    """A snapshot whose content can be verified after persistence or transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str = Field(min_length=1)
    kind: SnapshotKind
    as_of: date
    captured_at: datetime
    source: str = Field(min_length=1)
    payload: dict[str, Any]
    lineage_refs: tuple[str, ...] = ()
    content_hash: str = Field(pattern=SNAPSHOT_HASH_PATTERN)
    schema_version: str = SNAPSHOT_SCHEMA_VERSION


class ImmutableSnapshotBundle(BaseModel):
    """The three inputs that must share one as-of date for a release run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: date
    pit_universe: ImmutableSnapshot
    delisting: ImmutableSnapshot
    indicator_input: ImmutableSnapshot
    bundle_hash: str = Field(pattern=SNAPSHOT_HASH_PATTERN)
    schema_version: str = SNAPSHOT_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_kinds_and_date(self) -> ImmutableSnapshotBundle:
        snapshots = (self.pit_universe, self.delisting, self.indicator_input)
        if tuple(snapshot.kind for snapshot in snapshots) != SNAPSHOT_KINDS:
            raise ValueError("snapshot bundle must contain PIT, delisting, and indicator input kinds")
        if any(snapshot.as_of != self.as_of for snapshot in snapshots):
            raise ValueError("all immutable snapshots must share the bundle as_of date")
        return self


def _canonical_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=str))


def _snapshot_hash_payload(snapshot: ImmutableSnapshot) -> dict[str, Any]:
    return {
        "as_of": snapshot.as_of.isoformat(),
        "kind": snapshot.kind,
        "lineage_refs": list(snapshot.lineage_refs),
        "payload": snapshot.payload,
        "schema_version": snapshot.schema_version,
        "source": snapshot.source,
    }


def compute_snapshot_hash(snapshot: ImmutableSnapshot | Mapping[str, Any]) -> str:
    normalized = (
        snapshot
        if isinstance(snapshot, ImmutableSnapshot)
        else ImmutableSnapshot.model_validate(snapshot)
    )
    canonical = json.dumps(
        _snapshot_hash_payload(normalized),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def build_immutable_snapshot(
    *,
    kind: SnapshotKind,
    as_of: date | str,
    source: str,
    payload: Mapping[str, Any],
    lineage_refs: Sequence[str] = (),
    captured_at: datetime | None = None,
) -> ImmutableSnapshot:
    normalized_payload = _canonical_payload(payload)
    normalized_refs = tuple(sorted({str(ref) for ref in lineage_refs if str(ref).strip()}))
    snapshot = ImmutableSnapshot(
        snapshot_id=f"{kind}:{as_of}",
        kind=kind,
        as_of=as_of,
        captured_at=captured_at or datetime.now(UTC),
        source=source,
        payload=normalized_payload,
        lineage_refs=normalized_refs,
        content_hash="0" * SNAPSHOT_HASH_LENGTH,
    )
    content_hash = compute_snapshot_hash(snapshot)
    return snapshot.model_copy(
        update={
            "snapshot_id": f"{kind}:{snapshot.as_of.isoformat()}:{content_hash[:16]}",
            "content_hash": content_hash,
        }
    )


def compute_bundle_hash(bundle: ImmutableSnapshotBundle | Mapping[str, Any]) -> str:
    normalized = (
        bundle
        if isinstance(bundle, ImmutableSnapshotBundle)
        else ImmutableSnapshotBundle.model_validate(bundle)
    )
    canonical = json.dumps(
        {
            "as_of": normalized.as_of.isoformat(),
            "schema_version": normalized.schema_version,
            "snapshot_hashes": [
                normalized.pit_universe.content_hash,
                normalized.delisting.content_hash,
                normalized.indicator_input.content_hash,
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def build_snapshot_bundle(
    *,
    as_of: date | str,
    pit_universe: Mapping[str, Any],
    delisting: Mapping[str, Any],
    indicator_input: Mapping[str, Any],
    source: str,
    lineage_refs: Sequence[str] = (),
    captured_at: datetime | None = None,
) -> ImmutableSnapshotBundle:
    snapshots = {
        kind: build_immutable_snapshot(
            kind=kind,
            as_of=as_of,
            source=source,
            payload=payload,
            lineage_refs=lineage_refs,
            captured_at=captured_at,
        )
        for kind, payload in (
            ("pit_universe", pit_universe),
            ("delisting", delisting),
            ("indicator_input", indicator_input),
        )
    }
    bundle = ImmutableSnapshotBundle(
        as_of=as_of,
        pit_universe=snapshots["pit_universe"],
        delisting=snapshots["delisting"],
        indicator_input=snapshots["indicator_input"],
        bundle_hash="0" * SNAPSHOT_HASH_LENGTH,
    )
    return bundle.model_copy(update={"bundle_hash": compute_bundle_hash(bundle)})


def validate_snapshot_bundle(
    bundle: ImmutableSnapshotBundle | Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if bundle is None:
        return ("immutable snapshot bundle is missing",)
    try:
        normalized = (
            bundle
            if isinstance(bundle, ImmutableSnapshotBundle)
            else ImmutableSnapshotBundle.model_validate(bundle)
        )
    except ValueError as exc:
        return (f"immutable snapshot bundle schema error: {exc}",)

    errors: list[str] = []
    snapshots = (
        normalized.pit_universe,
        normalized.delisting,
        normalized.indicator_input,
    )
    if tuple(snapshot.kind for snapshot in snapshots) != SNAPSHOT_KINDS:
        errors.append("snapshot bundle kinds are not PIT, delisting, and indicator input")
    if any(snapshot.as_of != normalized.as_of for snapshot in snapshots):
        errors.append("all immutable snapshots must share the bundle as_of date")
    for snapshot in snapshots:
        if snapshot.content_hash != compute_snapshot_hash(snapshot):
            errors.append(f"snapshot content hash mismatch: {snapshot.kind}")
    if normalized.bundle_hash != compute_bundle_hash(normalized):
        errors.append("immutable snapshot bundle hash mismatch")
    return tuple(errors)
