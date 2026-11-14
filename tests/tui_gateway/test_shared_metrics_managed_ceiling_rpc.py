"""shared_metrics.status / shared_metrics.set under a managed ``telemetry.shared_metrics.send: false``: the
Desktop reads the lock, and an answer it sends anyway is stored without the send the ceiling forbids (#138804)."""

from __future__ import annotations

from pathlib import Path

import hermes_yaml as yaml

from hermes_cli import managed_scope
from tui_gateway import server


def _bind(monkeypatch, tmp_path: Path) -> Path:
    launch, worker, managed = tmp_path / "launch", tmp_path / "profiles" / "code", tmp_path / "managed"
    for home in (launch, worker, managed):
        home.mkdir(parents=True)
    for home in (launch, worker):
        (home / "config.yaml").write_text(yaml.safe_dump({"model": {"provider": "nous"}}), encoding="utf-8")
    (managed / "config.yaml").write_text(
        yaml.safe_dump({"telemetry": {"shared_metrics": {"send": False}}}), encoding="utf-8")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed))
    managed_scope.invalidate_managed_cache()
    monkeypatch.setattr(server, "_hermes_home", launch)
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.setattr(server, "_profile_home", lambda name: worker if (name or "").strip() == "code" else None)
    server._cfg_cache = server._cfg_sig = server._cfg_path = None
    return worker


def _call(method: str, params: dict) -> dict:
    return server._methods[method]("rid", params)["result"]


def test_status_reports_the_lock_and_set_stores_no_send(tmp_path, monkeypatch):
    worker = _bind(monkeypatch, tmp_path)
    locked = {"enabled": False, "send": False, "decided": True, "reask": False, "send_locked": True}

    assert _call("shared_metrics.status", {"profile": "code"}) == locked
    assert _call("shared_metrics.set", {"profile": "code", "enabled": True, "send": True}) == {**locked, "enabled": True}

    stored = yaml.safe_load((worker / "config.yaml").read_text(encoding="utf-8"))["telemetry"]["shared_metrics"]
    assert stored == {"enabled": True, "send": False, "offer_version": 2}
    managed_scope.invalidate_managed_cache()
