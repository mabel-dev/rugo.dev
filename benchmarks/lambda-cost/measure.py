"""Run the cold/warm matrix against every function, appending REPORT data to results.jsonl.

Each cold sample: change memory/env (retires the environment), invoke once.
Then WARM_N warm invocations on that same environment.
"""
import base64
import json
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config

from deploy import ARCHES, LIBS, REGION, fname

SHAPES = ["broad", "selective", "pruned", "footer"]
import os
MEMORY = [int(m) for m in os.environ.get("MEMORY", "1024,512").split(",")]
COLD_N = 5
WARM_N = 10

lam = boto3.client("lambda", region_name=REGION, config=Config(read_timeout=180, retries={"max_attempts": 5}))
lock = threading.Lock()
out = open(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl", "a")

FIELDS = {
    "duration": r"Duration: ([\d.]+) ms",
    "billed": r"Billed Duration: ([\d.]+) ms",
    "memory_size": r"Memory Size: (\d+) MB",
    "max_memory": r"Max Memory Used: (\d+) MB",
    "init": r"Init Duration: ([\d.]+) ms",
}


def parse_report(log):
    line = next(l for l in log.splitlines() if l.startswith("REPORT"))
    rec = {}
    for k, pat in FIELDS.items():
        m = re.search(pat, line)
        rec[k] = float(m.group(1)) if m else None
    rec["report"] = line
    return rec


def invoke(name, shape):
    r = lam.invoke(FunctionName=name, Payload=json.dumps({"shape": shape}), LogType="Tail")
    log = base64.b64decode(r["LogResult"]).decode()
    payload = json.loads(r["Payload"].read())
    rec = parse_report(log)
    rec["error"] = r.get("FunctionError")
    rec["payload"] = payload
    return rec


def retire(name, memory):
    lam.update_function_configuration(
        FunctionName=name,
        MemorySize=memory,
        Environment={"Variables": {**current_env(name), "NONCE": uuid.uuid4().hex}},
    )
    lam.get_waiter("function_updated_v2").wait(FunctionName=name)


def current_env(name):
    return lam.get_function_configuration(FunctionName=name)["Environment"]["Variables"]


def record(**rec):
    with lock:
        out.write(json.dumps(rec) + "\n")
        out.flush()


def run_function(lib, arch):
    name = fname(lib, arch)
    for memory in MEMORY:
        for shape in SHAPES:
            for i in range(COLD_N):
                retire(name, memory)
                rec = invoke(name, shape)
                record(lib=lib, arch=arch, memory=memory, shape=shape, kind="cold", i=i, **rec)
                if i == COLD_N - 1:
                    for j in range(WARM_N):
                        rec = invoke(name, shape)
                        record(lib=lib, arch=arch, memory=memory, shape=shape, kind="warm", i=j, **rec)
            print(time.strftime("%H:%M:%S"), name, memory, shape, "done", flush=True)


if __name__ == "__main__":
    with ThreadPoolExecutor(len(LIBS) * len(ARCHES)) as pool:
        futures = [pool.submit(run_function, lib, arch) for lib in LIBS for arch in ARCHES]
        for f in futures:
            f.result()
    print("matrix complete")
