# Openloop

An HTML website with a looping video introduction. Click the video to reveal
French text when the browser's preferred language is French, or English otherwise.

Run `uv run build.py` to generate the site in `build/`, then open
`build/index.html` in a browser. The build directory is ignored by Git.

## Content

- Edit `en/index.md` and `fr/index.md` for the introduction text.
- Add files such as `en/history.md` and `fr/histoire.md` to generate
  `build/history.html` and `build/histoire.html`. These pages show text
  immediately in their source language, regardless of the browser language.
- Filenames must be unique across `en/` and `fr/`. The two `index.md` files
  are the sole exception: they are combined into the bilingual landing page.
- Markdown supports paragraphs, `#` through `######` headings, `* item` bullet
  lists, `1. item` numbered lists, and `[label](URL)` links. Put each list item
  on its own line. Relative links to `.md` files become `.html` links.
- Put fixed assets in `assets/`. They are copied into `build/` with the same
  relative paths when missing or when their source timestamp is newer.
  The template is excluded from copying.
- Edit `assets/index.tmpl.html` to change the shared layout. It uses Python
  `str.format` placeholders `{en}`, `{fr}`, `{is_index}`, `{intro_hidden}`,
  `{autoplay}`, and `{language}`. Literal CSS and JavaScript braces must be doubled.
- The introduction plays `assets/open-loop.mp4` automatically, muted and looping.

Run `uv run build.py --sync` to build and then upload the generated site over SSH
to `root@server.swirly.com:~ax/public_html/loop/`, with owner and group `ax:ax`.
