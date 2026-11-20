"""Run every command in the draft posts against the rugo on your PATH.

    python3 drafts/verify_drafts.py              # every draft
    python3 drafts/verify_drafts.py schema       # drafts whose folder contains "schema"

Each draft is a folder holding one post (`<slug>.html`). The verifier makes an empty temp
directory per post and walks the post's code blocks in order:

  <pre><code class="language-bash">    run with `bash -c` (no `set -e`, so `cmd; echo "exit code: $?"`
                                       works). Fails if the last command exits non-zero.
  <pre><code class="language-output">  if it sits straight after a bash block, it is that block's expected
                                       output (stdout+stderr, trailing whitespace ignored,
                                       pytest timings like "in 0.85s" ignored).
  <pre><code data-save="path">         written to `path` in the temp dir, as a reader would save it.
  <pre><code data-append="path">       appended to `path` (blank line between).
  anything else                        not run (diagrams, AWS commands that need an account).

Files named test_*.py next to the post are copied in first (the post links to them).
Saved `.github/workflows/*.yml` files are linted with `actionlint` when it is on PATH.
Needs network access (samples come from rugo.dev/data). Put the rugo release under test on
PATH first, e.g.  python3 -m venv /tmp/v && /tmp/v/bin/pip install rugo && PATH=/tmp/v/bin:$PATH ...
Exit 1 if anything fails.
"""
import difflib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOCK = re.compile(r"<pre><code([^>]*)>(.*?)</code></pre>", re.S)
TIMEOUT = 300


def norm(text):
    text = re.sub(r"\bin \d+(\.\d+)?s\b", "in Ns", text)
    return "\n".join(ln.rstrip() for ln in text.strip("\n").splitlines()).strip("\n")


def attr(attrs, name):
    m = re.search(name + r'="([^"]*)"', attrs)
    return m.group(1) if m else None


def verify(post):
    # strip highlight spans (tools/highlight_code.py) before unescaping
    blocks = [(a, html.unescape(re.sub(r"</?span[^>]*>", "", c)))
              for a, c in BLOCK.findall(post.read_text(encoding="utf-8"))]
    failures, ran = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for extra in post.parent.glob("test_*.py"):
            shutil.copy(extra, work)
        env = {**os.environ, "PYTHONWARNINGS": "ignore", "PYTHONDONTWRITEBYTECODE": "1"}
        for i, (attrs, code) in enumerate(blocks):
            save, append = attr(attrs, "data-save"), attr(attrs, "data-append")
            if save or append:
                target = work / (save or append)
                target.parent.mkdir(parents=True, exist_ok=True)
                if append:
                    code = "\n\n" + code
                with open(target, "a" if append else "w", encoding="utf-8") as fh:
                    fh.write(code.rstrip("\n") + "\n")
                if target.suffix == ".yml" and shutil.which("actionlint"):
                    res = subprocess.run(["actionlint", str(target)], capture_output=True, text=True)
                    ran += 1
                    if res.returncode:
                        failures.append(f"block {i}: actionlint: {res.stdout}{res.stderr}")
                continue
            if "language-bash" not in attrs:
                continue
            ran += 1
            res = subprocess.run(["bash", "-c", code], cwd=work, env=env, capture_output=True,
                                 text=True, timeout=TIMEOUT)
            got = res.stdout + res.stderr
            if res.returncode:
                failures.append(f"block {i}: exit {res.returncode}\n{code}\n{got}")
                continue
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if nxt and "language-output" in nxt[0] and norm(nxt[1]) != norm(got):
                diff = "\n".join(difflib.unified_diff(norm(nxt[1]).splitlines(), norm(got).splitlines(),
                                                      "post", "actual", lineterm=""))
                failures.append(f"block {i}: output differs\n{code}\n{diff}")
    return ran, failures


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    rugo = shutil.which("rugo")
    if not rugo:
        sys.exit("error: `rugo` is not on PATH")
    print("rugo:", rugo)
    bad = 0
    for post in sorted(HERE.glob("*/*.html")):
        if pattern not in post.parent.name:
            continue
        ran, failures = verify(post)
        print(f"{'FAIL' if failures else 'ok  '} {post.relative_to(HERE)}  ({ran} steps run)")
        for f in failures:
            print("   " + f.replace("\n", "\n   "))
        bad += bool(failures)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
