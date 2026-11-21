#!/usr/bin/env python3
"""Remove only this plugin's exact QML insertions; refuse changed/ambiguous files."""
import runpy
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: unpatch-lock-howdy.py <Service.qml path>", file=sys.stderr)
        return 2
    module = runpy.run_path(str(Path(__file__).with_name("patch-lock-howdy.py")))
    text = Path(sys.argv[1]).read_text()
    if "omarchy-lock-howdy" not in text:
        print("Lock screen is not patched by Howdy.")
        return 0
    for old, new in reversed(module["PATCHES"]):
        alternatives = old.alternatives if isinstance(old, module["_MatchAny"]) else (old,)
        matches = []
        for original in alternatives:
            patched = new(original) if callable(new) else new
            if text.count(patched) == 1:
                matches.append((original, patched))
        if len(matches) != 1:
            print("Cannot safely reverse Howdy patch: upstream QML changed or anchors are ambiguous.", file=sys.stderr)
            return 1
        original, patched = matches[0]
        text = text.replace(patched, original, 1)
    if "omarchy-lock-howdy" in text:
        print("Howdy references remain after reversal; refusing to write.", file=sys.stderr)
        return 1
    Path(sys.argv[1]).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
