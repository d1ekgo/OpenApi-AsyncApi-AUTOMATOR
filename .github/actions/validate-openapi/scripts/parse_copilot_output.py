#!/usr/bin/env python3

import argparse
import html
import json
import re
from pathlib import Path


def write_env(path: Path, errors: int, warnings: int, failed: int):
    path.write_text(
        f"copilot_errors={errors}\n"
        f"copilot_warnings={warnings}\n"
        f"copilot_failed={failed}\n",
        encoding="utf-8",
    )


def fail(reason: str, input_text: str, output_md: Path, output_env: Path, output_reason: Path):
    out = (
        "copilotErrors: 0\n"
        "copilotWarnings: 0\n"
        f"⚠️ Copilot infra/parsing failure: {reason}\n\n"
        "Evidencia:\n\n"
        "```\n"
        f"{input_text[-2000:]}\n"
        "```\n"
    )
    output_md.write_text(out, encoding="utf-8")
    output_reason.write_text(reason, encoding="utf-8")
    write_env(output_env, 0, 0, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-env", required=True)
    parser.add_argument("--output-reason", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    prompt_path = Path(args.prompt)
    output_md = Path(args.output_markdown)
    output_env = Path(args.output_env)
    output_reason = Path(args.output_reason)

    text = input_path.read_text(encoding="utf-8", errors="replace")

    blocks = re.findall(r"```(?:yaml|yml)\s*(.*?)\s*```", text, flags=re.S | re.I)
    html_blocks = re.findall(
        r"<pre><code[^>]*language-(?:yaml|yml)[^>]*>(.*?)</code></pre>",
        text,
        flags=re.S | re.I,
    )
    blocks.extend([html.unescape(b) for b in html_blocks])
    blocks = [b.strip() for b in blocks if b.strip()]

    if not blocks and re.search(r"(?mi)^\s*(?:-\s*)?ruleId\s*:\s*", text):
        blocks = [text.strip()]

    if not blocks:
        plain = html.unescape(text)
        plain = re.sub(r"<[^>]+>", "", plain)

        match_errors = re.search(r"(?i)copilotErrors\s*:\s*(\d+)", plain)
        match_warnings = re.search(r"(?i)copilotWarnings\s*:\s*(\d+)", plain)

        if match_errors and match_warnings:
            errors = int(match_errors.group(1))
            warnings = int(match_warnings.group(1))

            if errors == 0 and warnings == 0:
                output_md.write_text(
                    "copilotErrors: 0\n"
                    "copilotWarnings: 0\n"
                    "✅ Sin hallazgos semánticos.\n",
                    encoding="utf-8",
                )
                output_reason.write_text("", encoding="utf-8")
                write_env(output_env, 0, 0, 0)
                return

            fail(
                f"Copilot declaró copilotErrors={errors}, copilotWarnings={warnings} pero no entregó bloques YAML parseables",
                text,
                output_md,
                output_env,
                output_reason,
            )
            return

        fail("Sin bloques YAML parseables", text, output_md, output_env, output_reason)
        return

    prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace")
    catalog_match = re.search(r"```json\s*(\{.*?\})\s*```", prompt_text, flags=re.S | re.I)

    if not catalog_match:
        fail("Catálogo JSON no encontrado", text, output_md, output_env, output_reason)
        return

    try:
        catalog = json.loads(catalog_match.group(1))
    except Exception:
        catalog = None

    if not isinstance(catalog, dict) or not catalog:
        fail("Catálogo inválido o vacío", text, output_md, output_env, output_reason)
        return

    catalog_canon = {
        re.sub(r"\s+", "", rule_id.lower().strip("`'\"")): rule_id
        for rule_id in catalog.keys()
    }

    seen = {}
    unknown_ids = set()
    missing_rule_id = 0

    for block in blocks:
        for entry in re.split(r"(?mi)^(?=\s*(?:-\s*)?severity\s*:)", block):
            entry = entry.strip()
            if not re.search(
                r"(?mi)^\s*(?:-\s*)?(severity|ruleId|rule|category|message|suggestion|evidence)\s*:",
                entry,
            ):
                continue

            entry = re.sub(
                r"(?mi)^\s*-\s*(?=(severity|ruleId|rule|category|location|message|suggestion|evidence)\s*:)",
                "",
                entry,
            )

            rid_match = re.search(r'(?mi)^\s*ruleId\s*:\s*"?([^"\n#]+)"?', entry)
            loc_match = re.search(r'(?mi)^\s*location\s*:\s*"?([^"\n#]+)"?', entry)

            rid_raw = rid_match.group(1).strip().strip("`'\"").rstrip(".,;:") if rid_match else ""
            if not rid_raw:
                missing_rule_id += 1
                continue

            rid_key = catalog_canon.get(re.sub(r"\s+", "", rid_raw.lower()), "")
            if not rid_key:
                unknown_ids.add(rid_raw)
                continue

            location = loc_match.group(1).strip() if loc_match else ""
            if (rid_key, location) not in seen:
                seen[(rid_key, location)] = entry

    errors = 0
    warnings = 0
    render = []

    for (rid_key, location), entry in sorted(seen.items()):
        meta = catalog[rid_key]

        replacements = [
            ("severity", meta["severity"]),
            ("rule", meta["rule"]),
            ("ruleId", rid_key),
            ("category", meta["category"]),
        ]

        for key, value in replacements:
            if key == "severity":
                line = f"{key}: {value}"
            else:
                line = f'{key}: "{value}"'

            if re.search(rf"(?mi)^\s*{key}\s*:", entry):
                entry = re.sub(rf"(?mi)^\s*{key}\s*:\s*.*$", line, entry, count=1)
            else:
                entry = line + "\n" + entry

        if location:
            if re.search(r"(?mi)^\s*location\s*:", entry):
                entry = re.sub(r"(?mi)^\s*location\s*:\s*.*$", f'location: "{location}"', entry, count=1)
            else:
                entry = f'location: "{location}"\n' + entry

        if meta["severity"] == "error":
            errors += 1
        else:
            warnings += 1

        render.append(f"[Regla Violada]: {rid_key}\n\n```yaml\n{entry}\n```")

    meta_fail = bool(unknown_ids) or missing_rule_id > 0

    if meta_fail and (errors + warnings) == 0:
        errors = 1

    out = f"copilotErrors: {errors}\n" f"copilotWarnings: {warnings}\n"

    if errors == 0 and warnings == 0:
        out += "✅ Sin hallazgos semánticos.\n"
    else:
        if meta_fail:
            out += "⚠️ Copilot devolvió salida fuera del catálogo/formato esperado; se omitió parte del reporte.\n"
        if render:
            out += "\n" + "\n\n".join(render)

    output_md.write_text(out, encoding="utf-8")
    output_reason.write_text("" if not meta_fail else "Salida fuera de catálogo", encoding="utf-8")
    write_env(output_env, errors, warnings, 0)


if __name__ == "__main__":
    main()
