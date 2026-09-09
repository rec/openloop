import re
import subprocess
from html import escape
from pathlib import Path
from shutil import copy2
from urllib.parse import urlsplit, urlunsplit

import tyro
from pydantic import BaseModel


class Build(BaseModel, frozen=True):
    """Build the bilingual website from Markdown and fixed assets."""

    root: Path = Path(__file__).resolve().parent
    sync: bool = False
    """Upload the generated site to server.swirly.com after building."""

    def run(self) -> None:
        pages: dict[str, dict[str, Path]] = {
            "index": {c: self.root / c / "index.md" for c in ("en", "fr")}
        }
        for language in ("en", "fr"):
            for source in sorted((self.root / language).glob("*.md")):
                if source.stem == "index":
                    continue
                if source.stem in pages:
                    raise ValueError(f"Duplicate Markdown filename: {source.name}")
                pages[source.stem] = {language: source}

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
        for name, sources in pages.items():
            translations = {"en": "", "fr": ""}
            translations.update(
                {c: render_markdown(p.read_text()) for c, p in sources.items()}
            )
            is_index = name == "index"
            html = template.format(
                **translations,
                is_index="true" if is_index else "false",
                intro_hidden="" if is_index else "hidden",
                autoplay="autoplay" if is_index else "",
                language=next(iter(sources)),
            )
            (output / f"{name}.html").write_text(html)

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


def render_markdown(text: str) -> str:
    """Render paragraphs, ATX headings, and inline Markdown links."""
    blocks: list[str] = []
    paragraph: list[str] = []
    for line in [*text.splitlines(), ""]:
        heading = re.fullmatch(r"(#{1,6})\s+(.*)", line)
        if not line.strip() or heading:
            if paragraph:
                blocks.append(f"<p>{render_links(' '.join(paragraph))}</p>")
                paragraph.clear()
            if heading:
                level = len(heading[1])
                blocks.append(f"<h{level}>{render_links(heading[2])}</h{level}>")
        else:
            paragraph.append(line.strip())
    return "\n".join(blocks)


def render_links(text: str) -> str:
    parts: list[str] = []
    end = 0
    for match in re.finditer(r"\[([^\]]+)\]\(([^\s)]+)\)", text):
        parts.append(escape(text[end : match.start()]))
        url = urlsplit(match[2])
        if not url.scheme and not url.netloc and url.path.endswith(".md"):
            url = url._replace(path=url.path[:-3] + ".html")
        parts.append(
            f'<a href="{escape(urlunsplit(url), quote=True)}">{escape(match[1])}</a>'
        )
        end = match.end()
    parts.append(escape(text[end:]))
    return "".join(parts)


if __name__ == "__main__":
    tyro.cli(Build).run()
