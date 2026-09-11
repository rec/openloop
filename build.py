import re
import subprocess
from html import escape
from pathlib import Path
from posixpath import dirname, normpath
from shutil import copy2
from urllib.parse import unquote, urlsplit

import tyro
from pydantic import BaseModel

TRANSLATED_STEMS = {
    ("en", "history"): "histoire",
    ("en", "rights"): "droits",
    ("en", "rules"): "règles",
    ("en", "technology"): "technologie",
    ("fr", "droits"): "rights",
    ("fr", "histoire"): "history",
    ("fr", "règles"): "rules",
    ("fr", "technologie"): "technology",
}


class Build(BaseModel, frozen=True):
    """Build the bilingual website from Markdown and fixed assets."""

    root: Path = Path(__file__).resolve().parent
    sync: bool = True
    """Upload the generated site to server.swirly.com after building."""

    def run(self) -> None:
        output = self.root / "build"
        output.mkdir(exist_ok=True)
        assets = self.root / "assets"
        template_path = assets / "index.tmpl.html"
        for source in sorted(assets.rglob("*")):
            if source.is_file() and source != template_path:
                destination = output / source.relative_to(assets)
                if (
                    not destination.exists()
                    or source.stat().st_mtime_ns > destination.stat().st_mtime_ns
                ):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    copy2(source, destination)

        template = template_path.read_text()
        sources_by_language = {
            language: markdown_sources(self.root / language)
            for language in ("en", "fr")
        }
        pages: list[str] = []
        for language, sources in sources_by_language.items():
            for source in sources:
                page = f"{language}/{source.stem}"
                content = render_markdown(source.read_text(), page)
                navigation = render_navigation(
                    language,
                    sources,
                    source.stem,
                    corresponding_page(language, source.stem, sources_by_language),
                )
                pages.append(
                    f'<article id="{escape(page, quote=True)}" lang="{language}" '
                    "hidden>\n"
                    f"{content}\n"
                    f"{navigation}\n</article>"
                )
        (output / "index.html").write_text(template.format(pages="\n".join(pages)))

        if self.sync:
            subprocess.run(
                [
                    "rsync",
                    "-av",
                    "-e",
                    "ssh",
                    "--chown=ax:ax",
                    f"{output}/",
                    "root@server.swirly.com:~ax/public_html/loop/",
                ],
                check=True,
            )


def render_markdown(text: str, page: str) -> str:
    """Render paragraphs, headings, lists, and inline Markdown links."""
    blocks: list[str] = []
    paragraph: list[str] = []
    list_tag = ""
    for line in [*text.splitlines(), ""]:
        heading = re.fullmatch(r"(#{1,6})\s+(.*)", line)
        item = re.fullmatch(r"(\*|\d+\.)\s+(.*)", line)
        tag = ("ul" if item[1] == "*" else "ol") if item else ""
        if list_tag and list_tag != tag:
            blocks.append(f"</{list_tag}>")
            list_tag = ""
        if not line.strip() or heading or item:
            if paragraph:
                blocks.append(f"<p>{render_links(' '.join(paragraph), page)}</p>")
                paragraph.clear()
            if heading:
                level = len(heading[1])
                blocks.append(f"<h{level}>{render_links(heading[2], page)}</h{level}>")
            elif item:
                if not list_tag:
                    list_tag = tag
                    blocks.append(f"<{list_tag}>")
                blocks.append(f"<li>{render_links(item[2], page)}</li>")
        else:
            paragraph.append(line.strip())
    return "\n".join(blocks)


def markdown_sources(directory: Path) -> list[Path]:
    """Return Markdown files with the landing page first."""
    return [
        directory / "index.md",
        *(p for p in sorted(directory.glob("*.md")) if p.name != "index.md"),
    ]


def corresponding_page(
    language: str, stem: str, sources_by_language: dict[str, list[Path]]
) -> str:
    """Return the other language's page corresponding to a source page."""
    other_language = "fr" if language == "en" else "en"
    translated_stem = TRANSLATED_STEMS.get((language, stem), stem)
    other_stems = {source.stem for source in sources_by_language[other_language]}
    if translated_stem not in other_stems:
        translated_stem = stem
    return f"{other_language}/{translated_stem}"


def render_navigation(
    language: str, sources: list[Path], current: str, other_page: str
) -> str:
    """Render links to pages available in one language."""
    links: list[str] = []
    for source in sources:
        name = source.stem
        attributes = f'href="#" data-page="{language}/{escape(name, quote=True)}"'
        if name == current:
            attributes += ' aria-current="page"'
        links.append(f"<a {attributes}>{escape(name)}</a>")
    other_language = "fr" if language == "en" else "en"
    links.append(
        f'<a class="language-toggle" href="#" data-page="{other_page}">'
        f".{other_language}</a>"
    )
    return '<nav aria-label="Pages">' + " ".join(links) + "</nav>"


def render_links(text: str, page: str) -> str:
    parts: list[str] = []
    end = 0
    for match in re.finditer(r"\[([^\]]+)\]\(([^\s)]+)\)", text):
        parts.append(escape(text[end : match.start()]))
        url = urlsplit(match[2])
        if not url.scheme and not url.netloc and url.path.endswith(".md"):
            target = normpath(f"{dirname(page)}/{unquote(url.path[:-3])}")
            attributes = f'href="#" data-page="{escape(target, quote=True)}"'
        else:
            attributes = f'href="{escape(match[2], quote=True)}"'
        parts.append(f"<a {attributes}>{escape(match[1])}</a>")
        end = match.end()
    parts.append(escape(text[end:]))
    return "".join(parts)


if __name__ == "__main__":
    tyro.cli(Build).run()
