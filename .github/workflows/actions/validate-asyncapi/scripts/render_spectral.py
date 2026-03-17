#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


def bucket(severity):
    try:
        sev = int(severity)
    except Exception:
        return "warning"
    return "error" if sev == 0 else "warning"


def to_jsonpath(path):
    jp = "$"
    if not isinstance(path, list):
        return jp

    for seg in path:
        if seg is None:
            continue

        if isinstance(seg, int) or (isinstance(seg, str) and seg.isdigit()):
            jp += f"[{seg}]"
            continue

        s = str(seg)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", s):
            jp += "." + s
        else:
            jp += "[" + json.dumps(s) + "]"

    return jp


def render_item(category, code, location, message):
    label = "❌ Error" if category == "error" else "⚠️ Warning"
    return (
        f"{label}\n"
        f"Regla: `{code}`\n"
        f"Ubicación: `{location}`\n"
        f"Mensaje: {(message or '').strip()}\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--render", required=True)
    parser.add_argument("--env", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    render_path = Path(args.render)
    env_path = Path(args.env)

    raw = input_path.read_text(encoding="utf-8", errors="replace").strip()

    failed = False
    try:
        data = json.loads(raw or "[]")
        if not isinstance(data, list):
            failed = True
            data = []
    except Exception:
        failed = True
        data = []

    if failed:
        input_path.write_text("[]", encoding="utf-8")
        env_path.write_text(
            "spectral_failed=1\n"
            "spectral_errors=1\n"
            "spectral_warnings=0\n",
            encoding="utf-8",
        )
        render_path.write_text("✅ Sin hallazgos.\n", encoding="utf-8")
        return

    errors = 0
    warnings = 0
    for item in data:
        if not isinstance(item, dict):
            continue

        sev = item.get("severity")
        try:
            sev = int(sev)
        except Exception:
            sev = None

        if sev == 0:
            errors += 1
        elif sev is not None and sev >= 1:
            warnings += 1

    env_path.write_text(
        f"spectral_failed=0\n"
        f"spectral_errors={errors}\n"
        f"spectral_warnings={warnings}\n",
        encoding="utf-8",
    )

    if not data:
        render_path.write_text("✅ Sin hallazgos.\n", encoding="utf-8")
        return

    errors_list = []
    warnings_list = []

    for item in data:
        if not isinstance(item, dict):
            continue

        category = bucket(item.get("severity"))
        code = str(item.get("code") or "")
        location = to_jsonpath(item.get("path") or [])
        message = str(item.get("message") or "")

        if category == "error":
            errors_list.append((code, location, message))
        else:
            warnings_list.append((code, location, message))

    parts = [render_item("error", c, l, m) for c, l, m in errors_list]
    parts += [render_item("warning", c, l, m) for c, l, m in warnings_list]

    render_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
