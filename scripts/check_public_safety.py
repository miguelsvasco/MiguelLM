from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?m)^\s*OPENAI_API_KEY\s*=\s*\S+"),
    re.compile("/home/" + "miguelsv/"),
    re.compile("/Users/" + "miguel/"),
]
BLOCKED_TRACKED_FILES = {
    ".env",
    ".env.local",
    "LOCAL_NOTES.md",
    "commands.md",
    "config/server.yaml",
}
BLOCKED_TRACKED_PREFIXES = ("persona/",)


def public_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    failures: list[str] = []
    for relative in public_files():
        path = ROOT / relative
        if not path.exists():
            continue
        if relative in BLOCKED_TRACKED_FILES or relative.startswith(BLOCKED_TRACKED_PREFIXES):
            failures.append("%s should not be tracked" % relative)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append("%s matches %s" % (relative, pattern.pattern))

    if failures:
        print("Public safety check failed:", file=sys.stderr)
        for failure in failures:
            print("- %s" % failure, file=sys.stderr)
        return 1
    print("Public safety check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
