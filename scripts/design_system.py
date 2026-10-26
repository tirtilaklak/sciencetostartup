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
# Read from the build's own list so the two cannot drift apart.
from observatory import REDESIGN_CSS  # noqa: E402
CASCADE = ("style.css", *REDESIGN_CSS, "icons.css")
# Literal colours wired to tokens. Every live use of each value shares the token's role.
WIRED = ("field", "field-border", "green-dark", "tray", "tray-border", "logo-dark", "hover", "wash",
         "band", "band-group", "band-rule", "rule-strong", "track", "bar-compare", "figure-rule",
         "mark-frame", "dialog-border", "scrim", "status", "status-rule", "link-status")
# White also paints other things, so on-green replaces it only in rules that set text on a green fill.
ON_GREEN_RULES = (".button-primary", "#compare-tray a", "#compare-tray .quiet")
HEX = re.compile(r"#([0-9a-fA-F]{3,8})(?![0-9a-fA-F])")
COMMENT = re.compile(r"/\*.*?\*/", re.S)
DECLARATION = re.compile(r"(?<![\w-])--([\w-]+)\s*:")
VAR_USE = re.compile(r"var\(\s*--([\w-]+)")


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


def blank_comments(css):
    """Comments become spaces of the same length, so positions still match the source."""
    return COMMENT.sub(lambda match: " " * len(match.group()), css)


def lift_root(css, names):
    """Lift token declarations out of top-level rules whose whole selector is :root.

    Returns the remaining CSS, the lifted (name, value, position) triples and problems.
    """
    plain = blank_comments(css)
    lifted, problems, out = [], [], []
    depth, rule_start, copied, i = 0, 0, 0, 0
    while i < len(plain):
        char = plain[i]
        if char == "{" and depth == 0:
            selector = plain[rule_start:i].strip()
            close = plain.find("}", i)
            body = plain[i + 1:close]
            declares = [m.group(1) for m in DECLARATION.finditer(body) if m.group(1) in names]
            if selector == ":root" and close != -1 and "{" not in body:
                keep = []
                for part in re.finditer(r"[^;]+", body):
                    name, sep, value = part.group().partition(":")
                    if sep and name.strip().startswith("--") and name.strip()[2:] in names:
                        at = i + 1 + part.start() + len(part.group()) - len(part.group().lstrip())
                        lifted.append((name.strip()[2:], value.strip(), at))
                    elif part.group().strip():
                        keep.append(css[i + 1 + part.start():i + 1 + part.end()].strip())
                begin = rule_start + len(plain[rule_start:i]) - len(plain[rule_start:i].lstrip())
                out.append(css[copied:begin])
                if keep:
                    out.append(css[begin:i + 1] + ";".join(keep) + "}")
                copied = rule_start = i = close + 1
                continue
            if declares and (":root" in selector or re.search(r"(?<![\w-])html(?![\w-])", selector)):
                problems.append(f"'{selector}' declares --{declares[0]}; only a rule whose whole selector is :root can be lifted")
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth == 0 and char in "};":
            rule_start = i + 1
        i += 1
    out.append(css[copied:])
    return "".join(out), lifted, problems


def build(tokens=None, web=ROOT / "web"):
    """Return {"files": {path: text}, "problems": [...], "summary": {...}}."""
    tokens = tokens or json.loads(TOKENS.read_text())
    values = token_values(tokens)
    shadows = {entry["name"]: entry["value"] for entry in tokens.get("shadow", {}).get("tokens", [])}
    problems, parts, lifted, declared, used = [], [], [], [], set()
    for index, name in enumerate(CASCADE):
        source = (web / name).read_text()
        css, found, issues = lift_root(source, set(values))
        lifted += [(token, value, (index, at)) for token, value, at in found]
        problems += [f"web/{name}: {issue}" for issue in issues]
        plain = blank_comments(source)
        declared += [(m.group(1), (index, m.start())) for m in DECLARATION.finditer(plain)]
        used |= {m.group(1) for m in VAR_USE.finditer(plain)}
        parts.append(f"/* ---- web/{name} ---- */\n{css.strip()}\n")
    stripped = "\n".join(parts)

    final = {token: value for token, value, _ in lifted}  # the last declaration wins, as in the cascade
    for name, value in final.items():
        if normal_hex(value.lower()) != normal_hex(values[name].lower()):
            problems.append(f"--{name}: tokens.json has {values[name]}, the stylesheet ends at {value}")
    # tokens.css loads first, so a lifted value must stay the last word on its variable.
    last = {}
    for token, _, at in lifted:
        last[token] = max(last.get(token, at), at)
    lifted_at = {(token, at) for token, _, at in lifted}
    for token, at in declared:
        if token in last and (token, at) not in lifted_at and at < last[token]:
            problems.append(f"--{token}: web/{CASCADE[at[0]]} declares it before its last top-level :root value; lifting would let that earlier declaration win")
    # The site must declare every token it reads; tokens.css would supply a value the site lacks.
    for token in sorted(used & set(values) - {token for token, _ in declared}):
        problems.append(f"var(--{token}) is used in web/ but the site never declares --{token}")

    css = stripped
    for name in WIRED + tuple(shadows) + ("on-green",):
        if re.search(r"var\(\s*--" + re.escape(name) + r"(?![\w-])", css):
            problems.append(f"var(--{name}) already appears in web/; wiring would be ambiguous")
    for name in WIRED:
        pattern = re.compile(re.escape(values[name]) + r"(?![0-9a-fA-F])", re.I)
        css, count = pattern.subn(f"var(--{name})", css)
        if not count:
            problems.append(f"{name}: {values[name]} no longer appears in web/; update tokens.json")
    for name, value in shadows.items():
        pattern = re.compile(r"(?<![\w#.-])" + re.escape(value) + r"(?![0-9a-fA-F\w])")
        css, count = pattern.subn(f"var(--{name})", css)
        if not count:
            problems.append(f"{name}: '{value}' no longer appears in web/; update tokens.json")
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
