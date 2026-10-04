#!/usr/bin/env bash
# Run the full matrix and write results/<stamp>/raw_<pass>.jsonl + env.txt. Then: ./report.py results/<stamp>
#
#   ./run.sh [--files N] [--repeat R] [--threads T] [--workloads "w1 w2"] [--skip-single]
#
#   --files N      first N files of data/jsonl (default: all)
#   --repeat R     timed runs per measurement, after one warm-up run (default 5)
#   --threads T    thread count for the multi-threaded pass (default: nproc)
#   --methods RE   only run measurements whose label matches the regex (the floor always runs)
#
# Two passes:
#   multi   all N files, T threads (C++), MAX_EXECUTION_WORKERS=T (Opteryx), rugo's own pool
#   single  one file (the first), every process pinned to one core with taskset; C++ and
#           Opteryx use one worker. rugo has no thread-count knob, so its pool runs on that
#           one core. (Linux only; skipped where taskset is missing.)
# The page cache is warmed before each pass and residency is recorded before and after.
set -uo pipefail
cd "$(dirname "$0")"
METHODS=""; FILES=0; REPEAT=5; THREADS=$(nproc 2>/dev/null || sysctl -n hw.ncpu); SKIP_SINGLE=0
WORKLOADS="parse filter_hi filter_lo minmax freq_lo freq_hi filter_agg deep langs"
while [ $# -gt 0 ]; do
    case $1 in
        --files) FILES=$2; shift ;;
        --repeat) REPEAT=$2; shift ;;
        --threads) THREADS=$2; shift ;;
        --workloads) WORKLOADS=$2; shift ;;
        --methods) METHODS=$2; shift ;;
        --skip-single) SKIP_SINGLE=1 ;;
        *) echo "unknown option $1"; exit 2 ;;
    esac
    shift
done
RUNS=$((REPEAT + 1))
PY=.venv/bin/python
ALL=$(ls data/jsonl/*.jsonl | sort)
[ "$FILES" -gt 0 ] && ALL=$(echo "$ALL" | head -n "$FILES")
NFILES=$(echo "$ALL" | wc -l | tr -d ' ')
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=results/$STAMP; mkdir -p "$OUT"
LOG=$OUT/progress.log
log() { echo "$(date -u +%H:%M:%S) $*" | tee -a "$LOG"; }

# A directory holding exactly the files in this pass, so a glob (Opteryx, rugo) and an
# explicit list (C++) name the same bytes.
mkset() {  # name files...
    local d=data/sets/$1; rm -rf "$d"; mkdir -p "$d"; shift
    for f in "$@"; do ln "$f" "$d/" 2>/dev/null || ln -s "$(pwd)/$f" "$d/"; done
    echo "$d"
}
warm() { for _ in 1 2; do cat "$@" > /dev/null; done; }
residency() { command -v fincore >/dev/null && fincore -b "$@" | awk 'NR>1{r+=$1; s+=$3} END{printf "page cache: %.1f%% of %.1f GB resident\n", 100*r/s, s/1e9}'; }

# ---------------------------------------------------------------- environment ---
{
    echo "stamp: $STAMP"; echo "files: $NFILES"; echo "workloads: $WORKLOADS"; [ -n "$METHODS" ] && echo "methods: $METHODS"; echo "repeat: $REPEAT (+1 warm-up)"; echo "threads: $THREADS"
    uname -a
    command -v lscpu >/dev/null && lscpu | grep -E "Model name|^CPU\(s\)|Thread|Core|Socket|NUMA node\(|L[123]|Flags" | sed 's/^Flags:.*\(avx512[a-z_]*\).*/Flags: (has \1 ...)/'
    sysctl -n machdep.cpu.brand_string 2>/dev/null
    free -g 2>/dev/null | head -2
    TOKEN=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null)
    [ -n "$TOKEN" ] && echo "ec2: $(curl -s -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type)"
    cat build/build_info.txt
    $PY -c "import sys, opteryx, rugo; print('python', sys.version.split()[0], '| opteryx', opteryx.__version__, '| rugo', rugo.__version__)"
    [ -f data/manifest.txt ] && echo "data manifest sha256: $(sha256sum data/manifest.txt 2>/dev/null | cut -c1-16)"
} > "$OUT/env.txt" 2>&1
cat "$OUT/env.txt"

# --------------------------------------------------------------------- matrix ---
one() {  # label cmd...   -> appends JSON lines to $RAW, logs a one-line summary
    local label=$1; shift
    if [ -n "$METHODS" ] && [[ $label != *floor ]] && ! [[ $label =~ $METHODS ]]; then return; fi
    local tmp; tmp=$(mktemp)
    if timeout 3600 "$@" > "$tmp" 2> "$tmp.err"; then
        cat "$tmp" >> "$RAW"
        log "  $label: $(grep -o '"seconds": *[0-9.]*' "$tmp" | grep -o '[0-9.]*$' | tail -n +2 | sort -n | head -1)s best"
    else
        log "  $label: FAILED ($(tail -c 300 "$tmp.err" | tr '\n' ' '))"
        echo "{\"label\":\"$label\",\"failed\":true}" >> "$RAW"
    fi
    rm -f "$tmp" "$tmp.err"
}

pass() {  # name threads pin set_dir
    local name=$1 t=$2 pin=$3 set=$4
    local files=$(ls "$set"/*.jsonl | sort)
    local glob="$set/*.jsonl"
    local P=""; [ -n "$pin" ] && P="taskset -c $pin"
    RAW=$OUT/raw_$name.jsonl
    warm $files; log "pass $name: $(echo $files | wc -w) files, threads=$t ${pin:+pinned to cpu $pin} | $(residency $files)"
    one "$name floor" $P ./build/bench_floor --workload parse --threads $t --repeat $RUNS $files
    local counted=0
    for w in $WORKLOADS; do
        log " $name $w"
        for api in ondemand ondemand-st dom dom-st; do
            [ $w = parse ] && [[ $api == ondemand* ]] && continue
            one "$name $w simdjson/$api" $P ./build/bench_simdjson --workload $w --api $api --threads $t --repeat $RUNS $files
        done
        one "$name $w yyjson/dom" $P ./build/bench_yyjson --workload $w --api dom --threads $t --repeat $RUNS $files
        one "$name $w sonic/dom" $P ./build/bench_sonic --workload $w --api dom --threads $t --repeat $RUNS $files
        [ $w != parse ] && one "$name $w sonic/ondemand" $P ./build/bench_sonic --workload $w --api ondemand --threads $t --repeat $RUNS $files
        if [ $w != parse ]; then
            local c=""; [ $counted = 0 ] && c="--count" && counted=1
            one "$name $w opteryx" env MAX_EXECUTION_WORKERS=$t $P $PY py/bench_opteryx.py --workload $w --source "$glob" --repeat $RUNS $c
        fi
        case $w in deep|langs) ;; *)
            one "$name $w rugo" $P $PY py/bench_rugo.py --workload $w --source "$glob" --repeat $RUNS
            [ "$t" -gt 1 ] && one "$name $w rugo fw=4" $P $PY py/bench_rugo.py --workload $w --source "$glob" --repeat $RUNS --file-workers 4 ;;
        esac
    done
    log "pass $name done | $(residency $files)"
}

SET_MULTI=$(mkset multi $ALL)
pass multi "$THREADS" "" "$SET_MULTI"
if [ $SKIP_SINGLE = 0 ] && command -v taskset >/dev/null; then
    SET_SINGLE=$(mkset single $(echo "$ALL" | head -1))
    pass single 1 2 "$SET_SINGLE"
fi
log "ALL DONE -> $OUT"
