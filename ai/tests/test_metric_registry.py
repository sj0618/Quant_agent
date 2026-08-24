from __future__ import annotations

from ai_graph import graph
from ai_graph.nodes.backtest import _profit_factor, _undefined_metric_availability
from ai_graph.quant_explanations import (
    PUBLIC_METRIC_KEYS,
    metric_explanation,
    metric_registry_provenance,
    public_metric_registry,
)


def test_profit_factor_uses_the_unclipped_engine_trade_pnl_ratio() -> None:
    # A 99% trade win rate used to synthesize and clip a value of 3.0. The actual
    # realized-PnL ratio is intentionally unrelated and must reach the report unchanged.
    summary = {"trade_win_rate": 0.99, "trade_profit_factor": 7.25}

    assert _profit_factor(summary) == 7.25


def test_profit_factor_is_unavailable_when_the_engine_cannot_measure_a_finite_ratio() -> None:
    assert _profit_factor({"trade_win_rate": 0.99}) is None
    assert _profit_factor({"trade_profit_factor": float("inf")}) is None
    assert _profit_factor({"trade_profit_factor": "7.25"}) is None


def test_metric_warning_variants_make_public_metrics_unavailable() -> None:
    assert _undefined_metric_availability(
        [{"metric": "profit_factor", "warning": "returned a non-finite value"}]
    ) == {
        "profit_factor": {
            "value": None,
            "unavailable_reason": "returned a non-finite value",
        }
    }


def test_public_metric_registry_is_complete_and_profit_factor_contract_is_explicit() -> None:
    registry = public_metric_registry()

    assert tuple(entry["key"] for entry in registry) == PUBLIC_METRIC_KEYS
    assert len({entry["key"] for entry in registry}) == len(PUBLIC_METRIC_KEYS)
    assert all(len(entry["implementation_hash"]) == 64 for entry in registry)

    profit_factor = metric_explanation("profit_factor")
    assert profit_factor["unit"] == "ratio"
    assert profit_factor["formula"] == "PF = Σ max(net_pnl, 0) / |Σ min(net_pnl, 0)|"
    assert profit_factor["denominator"] == "|Σ min(net_pnl, 0)| (손실 청산 거래의 절대 손익 합)"
    assert "승률 기반 프록시" in profit_factor["clip_policy"]
    assert "분모가 0" in profit_factor["null_policy"]
    assert "실현손익" in profit_factor["plain_explanation"]


def test_graph_metric_detail_carries_the_same_registry_provenance() -> None:
    detail = graph._metric_detail("sharpe_ratio", 1.25)
    registry = metric_registry_provenance("sharpe_ratio")

    assert detail.registry_version == registry["registry_version"]
    assert detail.provenance.implementation_path == registry["implementation_path"]
    assert detail.provenance.implementation_hash == registry["implementation_hash"]


def test_the_published_implementation_path_is_the_file_that_was_hashed() -> None:
    """Provenance that cannot be checked is decoration.

    The MR-ENG-01 row names "hash가 코드 변경에 뒤처질 위험" as this work's risk. The
    hash cannot lag, because it is computed from the source file at import time rather
    than written down - but only for as long as the path published beside it is the file
    that was actually read. Nothing tied those two together, so a path that drifted (a
    module moved, an entry copy-pasted from a neighbour) would publish a hash of one file
    under the name of another and still look consistent.

    Recomputing the digest here from the published path is what makes the pair
    falsifiable rather than self-consistent.
    """

    from hashlib import sha256
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[2]
    for key in PUBLIC_METRIC_KEYS:
        registry = metric_registry_provenance(key)
        source = repository_root / registry["implementation_path"]
        assert source.is_file(), f"{key} publishes a path that does not exist: {source}"
        assert registry["implementation_hash"] == sha256(source.read_bytes()).hexdigest(), (
            f"{key} publishes a hash that is not the digest of the file it names"
        )


def test_the_published_implementation_ref_names_something_importable() -> None:
    """The ref has to survive a rename, or it is a comment that looks like a reference.

    16 of the 18 public metrics share an implementation file with at least one other
    metric, so the path narrows the search to a file and the ref is what points inside
    it. A ref that no longer resolves sends a reader to a function that is not there.
    """

    from importlib import import_module

    def resolve(dotted: str) -> object:
        """Walk a dotted name that may end in a class and a method, not just a module."""

        parts = dotted.split(".")
        target = None
        for index in range(len(parts), 0, -1):
            try:
                target = import_module(".".join(parts[:index]))
            except ModuleNotFoundError:
                continue
            remainder = parts[index:]
            break
        else:
            raise AssertionError(f"no importable module prefix in {dotted}")
        for attribute in remainder:
            target = getattr(target, attribute)
        return target

    for key in PUBLIC_METRIC_KEYS:
        ref = metric_registry_provenance(key)["implementation_ref"]
        # Entries may describe a chain ("a.b.c → d.e.f"); the first element is the one
        # this registry row is responsible for.
        head = ref.split("→")[0].split("←")[0].strip()
        assert resolve(head) is not None, f"{key} names {head}, which does not resolve"
