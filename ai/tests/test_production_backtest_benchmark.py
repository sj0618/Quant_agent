from pathlib import Path

from scripts import run_production_backtest_benchmark as benchmark


def test_procfs_snapshot_ignores_process_exit_race(monkeypatch) -> None:
    vanished_process = Path("/proc/999999")

    monkeypatch.setattr(benchmark.os, "sysconf", lambda _name: 4096, raising=False)
    monkeypatch.setattr(Path, "iterdir", lambda _self: iter((vanished_process,)))

    def raise_process_lookup_error(
        _self: Path, *, encoding: str | None = None, errors: str | None = None
    ) -> str:
        del encoding, errors
        raise ProcessLookupError("process exited between /proc enumeration and read")

    monkeypatch.setattr(Path, "read_text", raise_process_lookup_error)

    assert benchmark._ProcessTreeSampler._procfs_snapshot(root_pid=999999) == (0, 0)
