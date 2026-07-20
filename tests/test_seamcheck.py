from __future__ import annotations

from pathlib import Path

import pytest

from vyper_scales.seamcheck.analyzer import analyze
from vyper_scales.seamcheck.manifest import ManifestError, load_manifest
from vyper_scales.seamcheck.render import render_json


def _project(tmp_path: Path, *, required: str = 'required = ["lossy-output"]') -> Path:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts" / "Router.vy").write_text(
        "def run(pool: address):\n    extcall IPool(\n        pool\n    ).exchange(0, 1, 1, 0)\n"
    )
    (tmp_path / "contracts" / "Pool.vy").write_text("# neighbor\n")
    (tmp_path / "tests" / "test_seam.py").write_text("def test_loss(): pass\n")
    manifest = tmp_path / "seams.toml"
    manifest.write_text(
        f"""version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "router.pool"
caller = "contracts/Router.vy"
target = "IPool(pool).exchange"
{required}
[[seams.evidence]]
test = "tests/test_seam.py::test_loss"
neighbor = "contracts/Pool.vy"
covers = ["lossy-output"]
"""
    )
    return manifest


def test_pass_when_required_evidence_and_call_exist(tmp_path: Path):
    report = analyze(load_manifest(_project(tmp_path)))
    assert report.status == "PASS"
    assert report.exit_code == 0
    assert '"status": "PASS"' in render_json(report)


def test_gap_when_required_dimension_is_missing(tmp_path: Path):
    report = analyze(
        load_manifest(_project(tmp_path, required='required = ["lossy-output", "revert-path"]'))
    )
    assert report.status == "GAP"
    assert report.seams[0].missing == ("revert-path",)
    assert report.exit_code == 1


def test_unregistered_external_call_fails_strict_policy(tmp_path: Path):
    manifest = _project(tmp_path)
    with (tmp_path / "contracts" / "Router.vy").open("a") as handle:
        handle.write("def read(feed: address):\n    staticcall IFeed(feed).price()\n")
    report = analyze(load_manifest(manifest))
    assert report.status == "GAP"
    assert len(report.unregistered) == 1


def test_missing_declared_call_is_error(tmp_path: Path):
    manifest = _project(tmp_path)
    text = manifest.read_text().replace("IPool(pool).exchange", "IPool(pool).remove_liquidity")
    manifest.write_text(text)
    report = analyze(load_manifest(manifest))
    assert report.status == "ERROR"
    assert report.exit_code == 2


def test_manifest_rejects_path_escape(tmp_path: Path):
    manifest = _project(tmp_path)
    manifest.write_text(manifest.read_text().replace("contracts/Router.vy", "../Router.vy"))
    with pytest.raises(ManifestError, match="escapes"):
        load_manifest(manifest)
