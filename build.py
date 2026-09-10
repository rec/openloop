import re
import subprocess
from html import escape
from pathlib import Path
from posixpath import dirname, normpath
from shutil import copy2
from urllib.parse import unquote, urlsplit

import tyro
from pydantic import BaseModel


class Build(BaseModel, frozen=True):
    """Build the bilingual website from Markdown and fixed assets."""

    root: Path = Path(__file__).resolve().parent
    sync: bool = False
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
        pages: list[str] = []
        for language in ("en", "fr"):
            directory = self.root / language
            sources = [directory / "index.md"]
            sources.extend(
                p for p in sorted(directory.glob("*.md")) if p.name != "index.md"
            )
            for source in sources:
                page = f"{language}/{source.stem}"
                content = render_markdown(source.read_text(), page)
                pages.append(
                    f'<article id="{escape(page, quote=True)}" lang="{language}" '
                    'tabindex="-1" hidden>\n'
                    f"{content}\n</article>"
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
