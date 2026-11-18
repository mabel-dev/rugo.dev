"""Run the validator handler against a mocked S3 (no AWS account needed).

    pip install rugo boto3 'moto[s3]' pytest
    curl -O https://rugo.dev/data/space_missions.parquet
    pytest -q test_handler.py
"""
import os
import urllib.parse

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

import boto3
import pytest
from moto import mock_aws

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.environ.get("SAMPLE", os.path.join(HERE, "space_missions.parquet"))
BUCKET = "lake"


def event_for(key):
    return {"Records": [{"s3": {"bucket": {"name": BUCKET},
                                "object": {"key": urllib.parse.quote_plus(key)}}}]}


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3")
        client.create_bucket(Bucket=BUCKET)
        import lambda_function
        lambda_function.s3 = client
        yield client


def put(s3, key, body):
    s3.put_object(Bucket=BUCKET, Key=key, Body=body)


def keys(s3):
    return sorted(o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []))


def run(key):
    import lambda_function
    return lambda_function.handler(event_for(key), None)[0]


def good():
    return open(SAMPLE, "rb").read()


def test_valid_file_is_promoted(s3):
    put(s3, "incoming/missions.parquet", good())
    result = run("incoming/missions.parquet")
    assert result["passed"] and result["problems"] == []
    assert keys(s3) == ["validated/missions.parquet"]
    tags = s3.get_object_tagging(Bucket=BUCKET, Key="validated/missions.parquet")["TagSet"]
    assert tags == [{"Key": "validation", "Value": "passed"}]


def test_key_with_space_is_decoded(s3):
    put(s3, "incoming/launch data.parquet", good())
    assert run("incoming/launch data.parquet")["passed"]
    assert keys(s3) == ["validated/launch data.parquet"]


def test_truncated_upload_is_quarantined(s3):
    put(s3, "incoming/cut.parquet", good()[:50_000])
    result = run("incoming/cut.parquet")
    assert not result["passed"]
    assert "not a readable Parquet file" in result["problems"][0]
    assert keys(s3) == ["quarantine/cut.parquet", "quarantine/cut.parquet.report.json"]


def test_not_parquet_is_quarantined(s3):
    put(s3, "incoming/notes.parquet", b"this is a csv in disguise\n")
    assert not run("incoming/notes.parquet")["passed"]


def test_empty_object_is_quarantined(s3):
    put(s3, "incoming/empty.parquet", b"")
    assert not run("incoming/empty.parquet")["passed"]


def test_schema_drift_is_quarantined(s3, tmp_path):
    # An exporter that started writing the timestamp column as text.
    import subprocess, sys
    csv_path = os.path.join(HERE, "space_missions.csv")
    if not os.path.exists(csv_path):
        pytest.skip("space_missions.csv not downloaded")
    out = tmp_path / "drift.parquet"
    subprocess.run([sys.executable, "-m", "rugo", "convert", csv_path, str(out)], check=True)
    put(s3, "incoming/drift.parquet", out.read_bytes())
    result = run("incoming/drift.parquet")
    assert result["problems"] == ["Lauched_at: expected timestamp[us], found varchar"]


def test_nulls_in_required_column(s3, tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    table = pq.read_table(SAMPLE)
    idx = table.schema.get_field_index("Company")
    values = table.column("Company").to_pylist()
    values[0] = None
    values[1] = None
    table = table.set_column(idx, "Company", pa.array(values, pa.string()))
    path = tmp_path / "nulls.parquet"
    pq.write_table(table, path)
    put(s3, "incoming/nulls.parquet", path.read_bytes())
    result = run("incoming/nulls.parquet")
    assert result["problems"] == ["Company: 2 null values"]


def test_damaged_body_is_quarantined(s3):
    # The footer is intact, but 25 KB in the middle of the file is overwritten.
    body = bytearray(good())
    body[5_000:30_000] = b"\xab" * 25_000
    put(s3, "incoming/damaged.parquet", bytes(body))
    result = run("incoming/damaged.parquet")
    assert not result["passed"]
    assert result["problems"][0].startswith("decode failed: row group 0, column 'Location'")
