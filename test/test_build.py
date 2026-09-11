from os import utime
from pathlib import Path
from shutil import copy2

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from build import Build, render_markdown


@pytest.fixture
def site(tmp_path: Path) -> Path:
    for name in ("en", "fr", "assets"):
        (tmp_path / name).mkdir()
    (tmp_path / "en/index.md").write_text("# Welcome\n\nRead [history](history.md).")
    (tmp_path / "fr/index.md").write_text(
        "# Bienvenue\n\nLire [l’histoire](histoire.md)."
    )
    copy2(
        Path(__file__).resolve().parents[1] / "assets/index.tmpl.html",
        tmp_path / "assets",
    )
    return tmp_path


def test_simple_markdown(file_regression: FileRegressionFixture) -> None:
    markdown = """# Title & text
A paragraph with <tags> and {braces}
continued on another line.

## Two
### Three
#### Four
##### Five
###### Six

[External](https://example.com/path.md?a=1&b=2) and [local](history.md#past).
[French](histoire.md?section=1#début), [email](mailto:hello@example.com).

*Literal asterisks* and plain text.
"""
    file_regression.check(render_markdown(markdown, "en/index"), extension=".html")


def test_index_combines_both_languages(
    site: Path, file_regression: FileRegressionFixture
) -> None:
    Build(root=site).run()
    file_regression.check((site / "build/index.html").read_text(), extension=".html")


def test_pages_with_matching_names_are_embedded(
    site: Path, file_regression: FileRegressionFixture
) -> None:
    (site / "en/history.md").write_text("# History\n\n[Français](../fr/history.md)")
    (site / "fr/history.md").write_text("# Histoire\n\n[Accueil](index.md)")
    Build(root=site).run()
    assert {p.name for p in (site / "build").iterdir()} == {"index.html"}
    file_regression.check((site / "build/index.html").read_text(), extension=".html")


def test_assets_are_copied_only_when_missing_or_newer(site: Path) -> None:
    source = site / "assets/images/logo.svg"
    source.parent.mkdir()
    source.write_text("original asset")
    utime(source, ns=(1_000_000_000, 1_000_000_000))
    Build(root=site).run()
    destination = site / "build/images/logo.svg"
    assert destination.read_text() == "original asset"
    assert destination.stat().st_mtime_ns == source.stat().st_mtime_ns

    destination.write_text("newer destination")
    utime(destination, ns=(2_000_000_000, 2_000_000_000))
    Build(root=site).run()
    assert destination.read_text() == "newer destination"

    source.write_text("updated source")
    utime(source, ns=(3_000_000_000, 3_000_000_000))
    Build(root=site).run()
    assert destination.read_text() == "updated source"
