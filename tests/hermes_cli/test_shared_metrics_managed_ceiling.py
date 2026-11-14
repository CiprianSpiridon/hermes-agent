"""A managed ``telemetry.shared_metrics.send: false`` is a ceiling every consent surface honours (#138804).

The resolver already refuses to send under it; these cover the surfaces that read and write the answer:
nothing offers sharing that cannot happen, and no answer stores a send the resolver would refuse. Each
test pins a real managed scope (``HERMES_MANAGED_DIR``) next to the sandboxed profile.
"""

from __future__ import annotations

import argparse

import pytest

import hermes_yaml as yaml


@pytest.fixture
def managed_dir(tmp_path, monkeypatch):
    managed = tmp_path / "managed"
    managed.mkdir()
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed))
    from hermes_cli import managed_scope

    def pin(shared_metrics: dict) -> None:
        (managed / "config.yaml").write_text(
            yaml.safe_dump({"telemetry": {"shared_metrics": shared_metrics}}), encoding="utf-8")
        managed_scope.invalidate_managed_cache()

    yield pin
    managed_scope.invalidate_managed_cache()


def _profile(shared_metrics: dict | None) -> None:
    from hermes_cli.config import save_config

    config = {"telemetry": {"shared_metrics": shared_metrics}} if shared_metrics is not None else {}
    save_config(config, strip_defaults=False)


def _state() -> dict:
    from hermes_cli.config import read_raw_config
    from hermes_cli.observability.shared_metrics_consent import consent_state

    return consent_state(read_raw_config())


def _stored() -> dict:
    from hermes_cli.config import read_raw_config

    return read_raw_config()["telemetry"]["shared_metrics"]


def test_the_ceiling_answers_the_offer_for_an_undecided_profile(managed_dir, monkeypatch):
    from hermes_cli.observability import shared_metrics_consent as consent

    asked = []
    monkeypatch.setattr("hermes_cli.curses_ui.curses_radiolist", lambda *a, **k: asked.append(a) or 0)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("HERMES_DESKTOP", raising=False)
    monkeypatch.delenv("HERMES_NONINTERACTIVE", raising=False)
    _profile(None)
    assert _state()["decided"] is False

    managed_dir({"send": False})
    consent.offer_consent_before_chat(argparse.Namespace())

    assert asked == []
    assert _state() == {"enabled": False, "send": False, "decided": True, "reask": False, "send_locked": True}


def test_an_opted_in_profile_reads_locked_and_keeps_its_own_collection(managed_dir):
    from hermes_cli.config import read_raw_config
    from hermes_cli.observability.shared_metrics_send_config import resolve_send_config

    _profile({"enabled": True, "send": True, "offer_version": 2})
    managed_dir({"send": False})

    assert _state() == {"enabled": True, "send": False, "decided": True, "reask": False, "send_locked": True}
    assert resolve_send_config(read_raw_config()).send is False


def test_no_answer_stores_a_send_the_ceiling_refuses(managed_dir, monkeypatch):
    from hermes_cli.observability.shared_metrics_consent import save_consent

    windows = []
    monkeypatch.setattr("hermes_cli.setup._record_send_consent_change", lambda *, enabled: windows.append(enabled))
    _profile(None)
    managed_dir({"send": False})

    save_consent(True, True)

    assert _stored() == {"enabled": True, "send": False, "offer_version": 2}
    assert windows == [False]


def test_setup_telemetry_does_not_ask_under_the_ceiling(managed_dir, monkeypatch):
    from hermes_cli.setup import setup_telemetry

    asked = []
    monkeypatch.setattr("hermes_cli.setup.prompt_yes_no", lambda question, default: asked.append(question) or True)
    managed_dir({"send": False})
    config: dict = {}

    setup_telemetry(config)

    assert asked == []
    assert config == {}


def test_a_managed_true_creates_no_lock_and_no_consent(managed_dir):
    from hermes_cli.observability.shared_metrics_consent import save_consent

    _profile(None)
    managed_dir({"send": True})

    assert _state() == {"enabled": False, "send": False, "decided": False, "reask": False, "send_locked": False}
    save_consent(True, True)
    assert _stored() == {"enabled": True, "send": True, "offer_version": 2}
