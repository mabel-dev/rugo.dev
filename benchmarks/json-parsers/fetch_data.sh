#!/usr/bin/env bash
# Download the JSONBench Bluesky dataset (the files JSONBench itself uses) and decompress it.
#
#   ./fetch_data.sh [N=100]     # N files of 1M documents each; 100 = ~48 GB of NDJSON
#
# Source: https://clickhouse-public-datasets.s3.amazonaws.com/bluesky/file_NNNN.json.gz
# Output: data/jsonl/file_NNNN.jsonl and data/manifest.txt (sizes + sha256 of each file).
set -euo pipefail
cd "$(dirname "$0")"
N=${1:-100}
mkdir -p data/gz data/jsonl
UNZ=$(command -v pigz >/dev/null && echo pigz || echo gzip)   # pigz is faster; gzip works
export UNZ
seq -f "https://clickhouse-public-datasets.s3.amazonaws.com/bluesky/file_%04g.json.gz" 1 "$N" |
    xargs -P 16 -n 1 wget -q --continue --directory-prefix data/gz
ls data/gz/*.json.gz | sort | head -n "$N" | xargs -P "$(nproc 2>/dev/null || echo 8)" -I{} bash -c '
    b=$(basename {} .json.gz)
    if [ ! -s data/jsonl/$b.jsonl ]; then
        $UNZ -dc {} > data/jsonl/$b.jsonl.tmp && mv data/jsonl/$b.jsonl.tmp data/jsonl/$b.jsonl
    fi'
ls data/jsonl/*.jsonl | sort | head -n "$N" | xargs -P 8 -n 4 sha256sum | sort -k2 > data/manifest.txt
echo "$(wc -l < data/manifest.txt) files, $(du -shc $(ls data/jsonl/*.jsonl | sort | head -n "$N") | tail -1 | cut -f1)"
