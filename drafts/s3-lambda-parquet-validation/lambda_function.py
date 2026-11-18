"""Validate Parquet files as they land in S3.

Trigger: S3 ObjectCreated on  incoming/*.parquet
Result:  passed -> validated/<name>      failed -> quarantine/<name> + <name>.report.json
Every object is also tagged validation=passed|failed.
"""
import json
import os
import urllib.parse

import boto3
from rugo import parquet

s3 = boto3.client("s3")

# The contract: column name -> the logical type rugo reports for it.
CONTRACT = {
    "Company": "varchar",
    "Location": "varchar",
    "Price": "float64",
    "Lauched_at": "timestamp[us]",
    "Rocket": "varchar",
    "Rocket_Status": "varchar",
    "Mission": "varchar",
    "Mission_Status": "varchar",
}
NOT_NULL = ["Company", "Mission", "Mission_Status"]


def validate(source):
    """Return a list of problems. An empty list means the file passed.

    `source` is a path or the bytes of the whole file.
    """
    # 1. Is it Parquet at all? The footer must parse.
    try:
        meta = parquet.read_metadata(source)
    except Exception as exc:
        return [f"not a readable Parquet file: {exc}"]

    problems = []
    if meta.num_rows == 0:
        problems.append("file has no rows")

    # 2. Does the schema match the contract?
    actual = {c.name: c.logical_type for c in meta.schema_columns}
    for name in CONTRACT.keys() - actual.keys():
        problems.append(f"missing column: {name}")
    for name in actual.keys() - CONTRACT.keys():
        problems.append(f"unexpected column: {name}")
    for name in CONTRACT.keys() & actual.keys():
        if actual[name] != CONTRACT[name]:
            problems.append(f"{name}: expected {CONTRACT[name]}, found {actual[name]}")
    if problems:
        return problems

    # 3. Does every row group decode, and do the row counts agree with the footer?
    try:
        decoded = 0
        with parquet.read_parquet(source) as reader:
            for morsel in reader:
                decoded += len(morsel)
        if decoded != meta.num_rows:
            problems.append(f"footer says {meta.num_rows} rows, decoded {decoded}")

        # 4. Are the columns that must never be null actually non-null?
        for name in NOT_NULL:
            with parquet.read_parquet(
                source, columns=[name], predicates=[(name, "is null", None)]
            ) as reader:
                nulls = sum(len(m) for m in reader)
            if nulls:
                problems.append(f"{name}: {nulls} null values")
    except Exception as exc:
        problems.append(f"decode failed: {exc}")
    return problems


def _tag(bucket, key, result):
    s3.put_object_tagging(
        Bucket=bucket,
        Key=key,
        Tagging={"TagSet": [{"Key": "validation", "Value": result}]},
    )


def _move(bucket, key, dest):
    s3.copy_object(
        Bucket=bucket, Key=dest, CopySource={"Bucket": bucket, "Key": key}
    )
    s3.delete_object(Bucket=bucket, Key=key)


def handler(event, context):
    results = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        # S3 URL-encodes keys in event notifications ("a b" arrives as "a+b").
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        name = key.split("/", 1)[1] if "/" in key else key
        local = "/tmp/" + os.path.basename(key)

        s3.download_file(bucket, key, local)
        try:
            problems = validate(local)
        finally:
            os.remove(local)  # /tmp persists on warm starts; don't fill it

        if problems:
            report = json.dumps({"key": key, "problems": problems}, indent=2)
            s3.put_object(
                Bucket=bucket,
                Key=f"quarantine/{name}.report.json",
                Body=report.encode(),
            )
            _tag(bucket, key, "failed")
            _move(bucket, key, f"quarantine/{name}")
        else:
            _tag(bucket, key, "passed")
            _move(bucket, key, f"validated/{name}")
        results.append({"key": key, "passed": not problems, "problems": problems})
    return results
