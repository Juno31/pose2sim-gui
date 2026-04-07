"""app/toml_bridge.py - Read/write Pose2Sim Config.toml, preserving comments."""

import os
import re


def load_toml(project_dir: str) -> dict:
    """Read the project's Config.toml and return as a nested dict. Returns {} on failure."""
    path = os.path.join(project_dir, "Config.toml")
    if not os.path.exists(path):
        return {}
    try:
        try:
            import tomllib          # Python 3.11+
            with open(path, "rb") as f:
                return tomllib.load(f)
        except ImportError:
            pass
        try:
            import tomli            # pip install tomli
            with open(path, "rb") as f:
                return tomli.load(f)
        except ImportError:
            pass
        import toml                 # pip install toml  (Pose2Sim dependency)
        with open(path, "r", encoding="utf-8") as f:
            return toml.load(f)
    except Exception:
        return {}


def _fmt(value) -> str:
    """Format a Python value as a TOML inline literal."""
    if value is None:
        return "'auto'"             # safe fallback for None values
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        return f"'{value}'"
    elif isinstance(value, (int, float)):
        import math
        if math.isnan(value) or math.isinf(value):
            return "'auto'"         # NaN/Inf are not valid TOML
        return str(value)
    elif isinstance(value, list):
        parts = ", ".join(_fmt(x) for x in value)
        return f"[{parts}]"
    else:
        return str(value)


def save_toml_values(project_dir: str, updates: list):
    """
    Section-aware in-place update of Config.toml.

    updates: list of (section, key, new_value) tuples, e.g.:
        [("pose", "pose_model", "Body_with_feet"),
         ("filtering.butterworth", "cut_off_frequency", 6)]

    Preserves all comments, whitespace and unrelated lines.
    """
    path = os.path.join(project_dir, "Config.toml")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Build lookup: (section, key) -> formatted_value_string
    lookup = {(s, k): _fmt(v) for s, k, v in updates}

    current_section = ""
    result = []

    for line in lines:
        stripped = line.strip()

        # Track [section] headers (not [[array-table]] headers)
        if stripped.startswith("[") and not stripped.startswith("[["):
            m = re.match(r"^\[([^\]]+)\]", stripped)
            if m:
                current_section = m.group(1).strip()

        replaced_line = line
        for (sect, key), val_str in lookup.items():
            if sect != current_section:
                continue
            # Match:  <whitespace> key <whitespace> = <whitespace> <value> <optional # comment>
            m = re.match(
                rf"^(\s*{re.escape(key)}\s*=\s*)([^#\n]*?)(\s*(?:#[^\n]*)?)(\n?)$",
                line,
            )
            if m:
                replaced_line = f"{m.group(1)}{val_str}{m.group(3)}{m.group(4)}"
                break

        result.append(replaced_line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(result)
