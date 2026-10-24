# Design system

The ScienceToStartup design system lives in a Design System artifact:
https://claude.ai/artifact/R9W9tG9MnXBzBhXSJ4Qxqx (private to its owner until shared).
It holds the brand book, 44 component guidelines and previews, the icons and the
favicon. This folder keeps the part that comes from code.

- `tokens.json`: the colours, type styles, spacing steps, radii, shadows, layout
  lengths and layers of the dashboard (`web/index.html`), each with its value and a
  usage note. It is the source for the artifact's `project/tokens.json`. The static
  company pages (`scripts/static_pages.py`) and `web/404.html` still use the first
  palette and are outside it.
- `../scripts/design_system.py`: builds the artifact's code-derived files from
  `web/` and this token file, using only the Python standard library.

## Build

```sh
python3 scripts/design_system.py --check
python3 scripts/design_system.py --output build/design-system
```

`--check` builds in memory and fails when a colour, a shadow or a lifted `:root`
variable in `web/` disagrees with `tokens.json`. Type, spacing, radius, layout and
z-index tokens describe the code, and the check does not track them. CI runs the
same checks through `tests/test_design_system.py`.

The build writes three files:

- `project/tokens.json`: the tokens, stamped with the current branch and commit.
- `project/components/bundle.css`: the site's live stylesheet in build order
  (`style.css`, `profiles-v2.css`, `work-v4.css`, `investor.css`, `edition.css`,
  `icons.css`). Root colour variables move into the tokens. 22 literal colours,
  white text on green fills and 5 shadows read as `var(--name)`.
- `tokens.css`: the tokens as CSS custom properties plus a class per type style,
  for pages outside the artifact. Load it before `bundle.css`.

## Why the bundle renders exactly like the site

The check swaps every `var(--name)` back for its token value. The text must come
out equal to the site's CSS with the lifted `:root` declarations removed. Three
more rules close the gaps that swap cannot see:

- Each lifted variable's last value in the cascade equals its token.
- No other declaration of a lifted variable comes before that last value, since
  `tokens.css` loads first and would hand the win to the earlier one.
- The site declares every token name it reads. Otherwise `tokens.css` would give
  `var(--name)` a value the site never had.

When these hold, the bundle and the site compute the same styles.

## When the CSS changes

- A colour that is already a token changed: update its value in `tokens.json`. The
  check names the token.
- A new colour or shadow with a clear role: add it to `tokens.json` with a usage
  note. For a literal colour, also add its name to `WIRED` in
  `scripts/design_system.py`. Then rebuild.
- Publish `project/tokens.json` and `project/components/bundle.css` from the build
  folder to the artifact. In Claude Code, ask to re-sync the design system from
  the repository.
