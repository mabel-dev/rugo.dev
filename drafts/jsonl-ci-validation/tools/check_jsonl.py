#!/usr/bin/env python3
"""Validate JSONL files against a contract. Exits 1 if any file fails.

    python tools/check_jsonl.py contract.json data/*.jsonl

contract.json:
    {"schema":   {"event_id": "INT64", "user": "VARCHAR", ...},
     "required": ["event_id", "user"]}
"""
import json
import os
import re
import sys

from rugo import jsonl


def problems(path, schema, required):
    """Return (list of problems, number of records) for one file."""
    # 1. Every line is valid JSON, and every value fits its declared type.
    #    rugo's error names the line (malformed JSON) or the column and value.
    try:
        rows = 0
        with jsonl.read_jsonl(path, explicit_schema=schema) as reader:
            for morsel in reader:
                rows += len(morsel)
    except Exception as exc:
        return [str(exc)], 0

    if rows == 0:
        return ["file has no records"], 0

    # 2. Required fields are present. An absent key counts as null.
    found = []
    for name in required:
        with jsonl.read_jsonl(
            path,
            columns=[name],
            predicates=[(name, "is null", None)],
            explicit_schema=schema,
        ) as reader:
            missing = sum(len(m) for m in reader)
        if missing:
            found.append(f"{name}: missing or null in {missing} of {rows} records")
    return found, rows


def annotate(path, message):
    """Print a GitHub Actions error annotation, pinned to a line when known."""
    line = re.search(r"at line (\d+)", message)
    where = f"file={path}" + (f",line={line.group(1)}" if line else "")
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error {where}::{escaped}")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    with open(argv[1]) as handle:
        contract = json.load(handle)
    schema, required = contract["schema"], contract.get("required", [])

    failed = 0
    for path in argv[2:]:
        found, rows = problems(path, schema, required)
        if not found:
            print(f"ok    {path}  ({rows} records)")
            continue
        failed += 1
        for message in found:
            print(f"FAIL  {path}: {message}")
            if os.environ.get("GITHUB_ACTIONS"):
                annotate(path, message)
    print(f"\n{len(argv) - 2 - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
