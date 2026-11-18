"""Run every command in the guides against the rugo on your PATH.

    python3 tools/verify_guides.py                  # all guides
    python3 tools/verify_guides.py parquet-footer   # guides whose filename contains this

For each guide it makes an empty temp directory and runs, in order, the front matter
`try_it` block and every ```bash block in the body, each as `bash -c`, the way you'd paste it into a terminal (no `set -e`, so the
`cmd; echo "exit code: $?"` pattern works). A block fails if its last command exits
non-zero. A ```output block straight after a bash block is the expected output: it must match
what the command printed (stdout and stderr, trailing whitespace ignored).

It needs network access (guides download their sample files from rugo.dev/data) and
the rugo release you want to check on PATH, e.g.:

    python3 -m venv /tmp/v && /tmp/v/bin/pip install -U rugo
    PATH=/tmp/v/bin:$PATH python3 tools/verify_guides.py

Run it with a python that has pyyaml; if you use pyenv, call that interpreter
directly (a pyenv shim puts its own bin dir ahead of yours on PATH, so you'd verify
whichever rugo pyenv has). The rugo version it ran against is printed at the top.

Exit 1 if any command fails or any output differs. Also warns when a guide's
`verified_with` isn't the rugo version it just ran against.
"""
import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "guides"
TIMEOUT = 120

FENCE = re.compile(r"^```(\w*)[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)


def rugo_version():
    exe = shutil.which("rugo")
    if not exe:
        sys.exit("error: `rugo` is not on PATH")
    try:
        python = Path(exe).read_text().splitlines()[0].removeprefix("#!").strip()
        out = subprocess.run(
            [python, "-c", "from importlib.metadata import version; print(version('rugo'))"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def norm(text):
    lines = [ln.rstrip() for ln in text.strip("\n").splitlines()]
    return "\n".join(lines).strip("\n")


def steps(path):
    """(label, command, expected-output-or-None) for every runnable block, in order."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.S)
    meta, body = yaml.safe_load(m.group(1)) or {}, m.group(2)
    out = []
    if meta.get("try_it"):
        out.append(("try_it", str(meta["try_it"]), None))
    blocks = list(FENCE.finditer(body))
    for i, b in enumerate(blocks):
        lang, code = b.group(1), b.group(2)
        line = body[: b.start()].count("\n") + 1
        if lang == "bash":
            expected = None
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            # only an *adjacent* output fence belongs to this command
            if nxt and nxt.group(1) == "output" and body[b.end():nxt.start()].strip() == "":
                expected = nxt.group(2)
            out.append((f"body line {line}", code, expected))
        elif lang == "output":
            prev = blocks[i - 1] if i else None
            if not (prev and prev.group(1) == "bash" and body[prev.end():b.start()].strip() == ""):
                raise SystemExit(f"{path.name}: body line {line}: ```output block must directly follow a ```bash block")
    return meta, out


def run(path):
    meta, plan = steps(path)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="rugo-guide-") as tmp:
        for label, code, expected in plan:
            try:
                p = subprocess.run(
                    ["bash", "-c", code],
                    cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                print(f"  FAIL {label}: timed out after {TIMEOUT}s")
                failures += 1
                continue
            first = code.strip().splitlines()[0]
            if p.returncode != 0:
                print(f"  FAIL {label}: exit {p.returncode}: {first}")
                print("       " + norm(p.stdout).replace("\n", "\n       "))
                failures += 1
            elif expected is not None and norm(p.stdout) != norm(expected):
                print(f"  FAIL {label}: output differs: {first}")
                diff = difflib.unified_diff(
                    norm(expected).splitlines(), norm(p.stdout).splitlines(), "guide", "actual", lineterm="", n=1
                )
                print("       " + "\n       ".join(diff))
                failures += 1
            else:
                print(f"  ok   {label}: {first}" + ("  (output matches)" if expected is not None else ""))
    return meta, failures


def main():
    want = sys.argv[1:]
    paths = [p for p in sorted(SRC.glob("*.md")) if not p.name.startswith("_") and (not want or any(w in p.name for w in want))]
    if not paths:
        sys.exit("no guides matched")
    version = rugo_version()
    print(f"rugo {version}\n")
    total = 0
    for path in paths:
        print(path.name)
        meta, failures = run(path)
        total += failures
        stamp = str(meta.get("verified_with") or "")
        if stamp and stamp != version:
            print(f"  note: front matter says verified_with {stamp}, but this ran against rugo {version}")
    print()
    if total:
        sys.exit(f"{total} step(s) failed")
    print(f"all commands in {len(paths)} guide(s) ran as written against rugo {version}")


if __name__ == "__main__":
    main()
