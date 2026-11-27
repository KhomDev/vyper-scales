from __future__ import annotations

from pathlib import Path

import pytest

from vyper_scales.seamcheck.analyzer import analyze
from vyper_scales.seamcheck.cli import main
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


def _manifest(tmp_path: Path, source: str, body: str) -> Path:
    (tmp_path / "contracts").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "contracts" / "Router.vy").write_text(source)
    (tmp_path / "tests" / "test_seam.py").write_text(
        "class TestSeam:\n    def test_loss(self):\n        pass\n"
    )
    manifest = tmp_path / "seams.toml"
    manifest.write_text(body)
    return manifest


def test_subscript_targets_and_literal_brackets_match(tmp_path: Path):
    manifest = _manifest(
        tmp_path,
        "def run():\n"
        "    extcall IERC20(tokens[i]).transfer(to, amount)\n"
        '    raw_call(empty(address), b"")\n'
        '    raw_call(targets[i], method_id("foo()"))\n',
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "transfer"
caller = "contracts/Router.vy"
target = "IERC20(tokens[i]).transfer"
required = []
[[seams]]
id = "empty"
caller = "contracts/Router.vy"
target = "empty(address).raw_call"
call_kind = "raw_call"
required = []
[[seams]]
id = "indexed"
caller = "contracts/Router.vy"
target = "targets[i].raw_call"
call_kind = "raw_call"
required = []
""",
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "PASS"
    assert report.unassessed == ()
    assert {site.target for site in report.seams[0].sites} == {"IERC20(tokens[i])"}


def test_method_name_does_not_cover_a_different_target(tmp_path: Path):
    manifest = _manifest(
        tmp_path,
        "def run():\n"
        "    extcall IERC20(self.a).transfer(self.b, 1)\n"
        "    extcall IERC20(self.b).transfer(self.a, 1)\n",
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "one"
caller = "contracts/Router.vy"
target = "IERC20(self.a).transfer"
required = []
""",
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "GAP"
    assert len(report.unregistered) == 1
    assert report.unregistered[0].target == "IERC20(self.b)"


def test_strings_comments_and_docstrings_are_not_calls(tmp_path: Path):
    manifest = _manifest(
        tmp_path,
        '"""\nextcall IERC20(self.hidden).transfer(to, 1)\n"""\n'
        "def run():\n"
        '    note: String[80] = "extcall IERC20(self.token).transfer("\n'
        "    # extcall IERC20(self.comment).approve(self.spender, 1)\n"
        "    extcall IERC20(self.token).approve(self.spender, 1)\n",
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "approve"
caller = "contracts/Router.vy"
target = "IERC20(self.token).approve"
required = []
""",
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "PASS"
    assert report.unregistered == ()


def test_unclassified_call_is_unassessed_and_not_ignorable(tmp_path: Path):
    manifest = _manifest(
        tmp_path,
        "def run():\n    extcall IERC20(self.token).approve(self.spender, 1)\n    extcall\n",
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
ignore_calls = ["*"]
[[seams]]
id = "approve"
caller = "contracts/Router.vy"
target = "IERC20(self.token).approve"
required = []
""",
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "UNASSESSED"
    assert report.exit_code == 3
    assert report.unassessed[0].kind == "extcall"
    assert "UNASSESSED" in render_json(report)


def test_missing_test_function_is_an_error(tmp_path: Path):
    manifest = _project(tmp_path)
    manifest.write_text(
        manifest.read_text().replace("test_seam.py::test_loss", "test_seam.py::test_missing")
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "ERROR"
    assert report.exit_code == 2
    assert any("test_missing" in error for error in report.seams[0].errors)


def test_class_and_parametrized_selectors_resolve(tmp_path: Path):
    manifest = _manifest(
        tmp_path,
        "def run():\n    extcall IPool(pool).exchange(0, 1, 1, 0)\n",
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "pool"
caller = "contracts/Router.vy"
target = "IPool(pool).exchange"
required = ["lossy-output"]
[[seams.evidence]]
test = "tests/test_seam.py::TestSeam::test_loss[1]"
covers = ["lossy-output"]
""",
    )
    report = analyze(load_manifest(manifest))
    assert report.status == "PASS"


def test_symlink_outside_manifest_root_is_rejected(tmp_path: Path):
    project = tmp_path / "proj"
    (project / "contracts").mkdir(parents=True)
    outside = tmp_path / "Outside.vy"
    outside.write_text("def x():\n    extcall IPool(self.pool).exchange()\n")
    (project / "contracts" / "Local.vy").write_text("def y():\n    pass\n")
    (project / "contracts" / "Linked.vy").symlink_to(outside)
    manifest = project / "seams.toml"
    manifest.write_text(
        """
version = 1
[project]
sources = ["contracts"]
[[seams]]
id = "local"
caller = "contracts/Local.vy"
target = "missing.call"
required = []
"""
    )
    with pytest.raises(ManifestError, match="escapes"):
        analyze(load_manifest(manifest))


def test_invalid_toml_and_output_errors_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    manifest = tmp_path / "seams.toml"
    manifest.write_bytes(b"version = [\n")
    assert main(["--manifest", str(manifest)]) == 2
    assert "Traceback" not in capsys.readouterr().err
    manifest.write_bytes(b"\xff")
    with pytest.raises(ManifestError, match="UTF-8"):
        load_manifest(manifest)

    good = _project(tmp_path)
    output = tmp_path / "report-dir"
    output.mkdir()
    assert main(["--manifest", str(good), "--output", str(output)]) == 2


def test_shipped_example_and_reference_router_are_classified(tmp_path: Path):
    root = Path(__file__).parents[1]
    report = analyze(load_manifest(root / "examples" / "seamcheck" / "seams.toml"))
    assert report.status == "PASS"
    assert report.exit_code == 0
    assert main(["--manifest", str(root / "examples" / "seamcheck" / "seams.toml")]) == 0

    router = (root / "examples" / "sig-matrix" / "contracts" / "SignatureRouter.vy").read_text()
    manifest = _manifest(
        tmp_path,
        router,
        """
version = 1
[project]
sources = ["contracts"]
strict_unregistered = true
[[seams]]
id = "erc1271"
caller = "contracts/Router.vy"
target = "signer.raw_call"
call_kind = "raw_call"
required = []
""",
    )
    scanned = analyze(load_manifest(manifest))
    assert scanned.status == "PASS"
    assert scanned.seams[0].sites[0].target == "signer"
    assert scanned.unassessed == ()


def test_article_quotes_the_shipped_seamcheck_report(capsys: pytest.CaptureFixture[str]):
    root = Path(__file__).parents[1]
    assert main(["--manifest", str(root / "examples" / "seamcheck" / "seams.toml")]) == 0
    output = capsys.readouterr().out.strip()
    article = (root / "articles" / "01-the-seam-is-the-security-boundary.md").read_text()
    assert output in article
