#!/usr/bin/env python3
"""Build the design system's code-derived files from web/ and design-system/tokens.json.

Writes project/tokens.json and project/components/bundle.css, the two files of the
Design System artifact that come from code, plus tokens.css for use outside it.
bundle.css is the site's live stylesheet in build order with token values read as
var(--name). --check builds in memory and proves that swapping every var() back for
its token value gives the site's own CSS again, so the two render identically.
"""
import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "design-system/tokens.json"
# The order scripts/observatory.py inlines these into index.html; later rules win.
CASCADE = ("style.css", "profiles-v2.css", "work-v4.css", "investor.css", "edition.css", "icons.css")
# Literal colours wired to tokens. Every live use of each value shares the token's role.
WIRED = ("field", "field-border", "green-dark", "tray", "tray-border", "logo-dark", "hover", "wash",
         "band", "band-group", "band-rule", "rule-strong", "track", "bar-compare", "figure-rule",
         "mark-frame", "dialog-border", "scrim", "status", "status-rule", "link-status", "focus-work")
# White also paints other things, so on-green replaces it only in rules that set text on a green fill.
ON_GREEN_RULES = (".button-primary", "#compare-tray a", "#compare-tray .quiet")
HEX = re.compile(r"#([0-9a-fA-F]{3,8})(?![0-9a-fA-F])")


def normal_hex(text):
    """Lowercase hex colours and expand #rgb/#rgba so equal colours compare equal."""
    def expand(match):
        digits = match.group(1).lower()
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        return "#" + digits
    return HEX.sub(expand, text)


def token_values(tokens):
    """Every token family but type, as name -> value (colours at their first theme)."""
    first = tokens["color"]["themes"][0]["id"]
    values = {}
    for key, family in tokens.items():
        if key in ("type", "meta") or not isinstance(family, dict) or "tokens" not in family:
            continue
        for entry in family["tokens"]:
            value = entry["value"]
            values[entry["name"]] = value[first] if isinstance(value, dict) else value
    return values


def lift_root(css, names):
    """Remove top-level :root declarations of token names; return the CSS and what was lifted."""
    lifted, out, depth, i = [], [], 0, 0
    while i < len(css):
        if depth == 0 and css.startswith(":root{", i):
            end = css.index("}", i)
            keep = []
            for declaration in filter(str.strip, css[i + 6:end].split(";")):
                name, _, value = declaration.partition(":")
                name = name.strip()
                if name.startswith("--") and name[2:] in names:
                    lifted.append((name[2:], value.strip()))
                else:
                    keep.append(declaration.strip())
            if keep:
                out.append(":root{" + ";".join(keep) + "}")
            i = end + 1
            continue
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        out.append(css[i])
        i += 1
    return "".join(out), lifted


def build(tokens=None, web=ROOT / "web"):
    """Return {"files": {path: text}, "problems": [...], "summary": {...}}."""
    tokens = tokens or json.loads(TOKENS.read_text())
    values = token_values(tokens)
    shadows = {entry["name"]: entry["value"] for entry in tokens.get("shadow", {}).get("tokens", [])}
    problems, parts, lifted = [], [], []
    for name in CASCADE:
        css, found = lift_root((web / name).read_text(), set(values))
        lifted += found
        parts.append(f"/* ---- web/{name} ---- */\n{css.strip()}\n")
    stripped = "\n".join(parts)

    final = dict(lifted)  # the last declaration wins, as in the cascade
    for name, value in final.items():
        if normal_hex(value.lower()) != normal_hex(values[name].lower()):
            problems.append(f"--{name}: tokens.json has {values[name]}, the stylesheet ends at {value}")

    css = stripped
    for name in WIRED + tuple(shadows) + ("on-green",):
        if f"var(--{name})" in css:
            problems.append(f"var(--{name}) already appears in web/; wiring would be ambiguous")
    for name in WIRED:
        pattern = re.compile(re.escape(values[name]) + r"(?![0-9a-fA-F])", re.I)
        css, count = pattern.subn(f"var(--{name})", css)
        if not count:
            problems.append(f"{name}: {values[name]} no longer appears in web/; update tokens.json")
    for name, value in shadows.items():
        if value not in css:
            problems.append(f"{name}: '{value}' no longer appears in web/; update tokens.json")
        css = css.replace(value, f"var(--{name})")
    for selector in ON_GREEN_RULES:
        rule = re.compile(r"((?:^|[}\n,])" + re.escape(selector) + r"\{[^}]*?(?<![-\w])color:)#fff(?![0-9a-fA-F])", re.I)
        css, count = rule.subn(r"\1var(--on-green)", css)
        if not count:
            problems.append(f"on-green: '{selector}' no longer sets color:#fff; update ON_GREEN_RULES")

    # Swap every var() back for its value: the text must be the site's CSS again.
    restored = css.replace("var(--on-green)", values["on-green"])
    for name in WIRED:
        restored = restored.replace(f"var(--{name})", values[name])
    for name, value in shadows.items():
        restored = restored.replace(f"var(--{name})", value)
    if normal_hex(restored) != normal_hex(stripped):
        problems.append("bundle.css does not restore to the site's CSS; a replacement changed more than a value")

    header = ("/* ScienceToStartup: the site's live stylesheet, in build order (scripts/observatory.py).\n"
              "   Token values live in tokens.json; this file reads them as var(--name). */\n")
    stamped = json.loads(json.dumps(tokens))
    stamped.setdefault("meta", {}).update(git_ref())
    files = {
        "project/tokens.json": json.dumps(stamped, indent=2, ensure_ascii=False) + "\n",
        "project/components/bundle.css": header + css,
        "tokens.css": compile_tokens(tokens),
    }
    root_vars = re.findall(r"(?:^|[}\n])\s*:root\{([^}]*)\}", css)
    unlifted = sorted({d.split(":")[0].strip()[2:] for block in root_vars for d in block.split(";") if d.strip().startswith("--")})
    summary = {"lifted": len(final), "wired": len(WIRED), "shadows": len(shadows), "unlifted": unlifted}
    return {"files": files, "problems": problems, "summary": summary}


def compile_tokens(tokens):
    """tokens.css as the Design System page compiles it: custom properties and a class per type style."""
    values = token_values(tokens)
    colour = [entry["name"] for entry in tokens["color"]["tokens"]]
    shadow = [entry["name"] for entry in tokens.get("shadow", {}).get("tokens", [])]
    first = tokens["color"]["themes"][0]["id"]

    def css_value(value):
        alias = re.fullmatch(r"\{(.+)\}", value)
        return f"var(--{alias.group(1)})" if alias else value
    lines = [f"/* {tokens.get('name', '')} — generated from tokens.json */",
             f':root, [data-theme="{first}"] {{ ' + " ".join(f"--{n}: {css_value(values[n])};" for n in colour + shadow) + " }",
             ":root { " + " ".join(f"--{n}: {v};" for n, v in values.items() if n not in colour + shadow)
             + "".join(f" --font-{k}: {stack};" for k, stack in tokens["type"]["families"].items()) + " }"]
    for group in tokens["type"]["groups"]:
        for style in group["styles"]:
            rules = [f"font-family: var(--font-{style.get('family', group.get('family'))});", f"font-size: {style['fontSize']};"]
            if "lineHeight" in style:
                rules.append(f"line-height: {style['lineHeight']};")
            rules.append(f"font-weight: {style['fontWeight']};")
            if "letterSpacing" in style:
                rules.append(f"letter-spacing: {style['letterSpacing']};")
            lines.append(f".{style['name']} {{ " + " ".join(rules) + " }")
    return "\n".join(lines) + "\n"


def git_ref():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return {}
    return {"ref": f"{branch}@{sha}", "synced": datetime.date.today().isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/design-system")
    parser.add_argument("--check", action="store_true", help="Build in memory and fail if tokens and CSS disagree.")
    args = parser.parse_args()
    result = build()
    if result["problems"]:
        raise SystemExit("Design system is out of step with web/:\n- " + "\n- ".join(result["problems"]))
    if args.check:
        print(json.dumps({"status": "passed", **result["summary"]}))
        return
    destination = args.output.resolve()
    if destination in (ROOT, ROOT / "web", ROOT / "dist", ROOT / "data", ROOT / "design-system"):
        raise SystemExit("Choose a separate output directory.")
    for path, text in result["files"].items():
        (destination / path).parent.mkdir(parents=True, exist_ok=True)
        (destination / path).write_text(text)
    print(json.dumps({"status": "built", "output": str(destination), **result["summary"]}))


if __name__ == "__main__":
    main()
