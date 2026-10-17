"""Create (or tear down) the benchmark stack: one bucket, one role, eight functions."""
import json
import sys
import time

import boto3

PREFIX = "rugo-cost-bench"
REGION = "us-east-1"
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]
BUCKET = f"{PREFIX}-{ACCOUNT}"
ROLE = f"{PREFIX}-role"
LIBS = ["rugo", "pyarrow", "duckdb", "polars"]
ARCHES = {"x86_64": "x86_64", "aarch64": "arm64"}

s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=REGION)


def fname(lib, arch):
    return f"{PREFIX}-{lib}-{ARCHES[arch]}"


def up():
    s3.create_bucket(Bucket=BUCKET)
    s3.upload_file("events.parquet", BUCKET, "events.parquet")
    for lib in LIBS:
        for arch in ARCHES:
            s3.upload_file(f"build/{lib}-{arch}.zip", BUCKET, f"code/{lib}-{arch}.zip")

    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    role_arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    iam.attach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    iam.put_role_policy(
        RoleName=ROLE,
        PolicyName="read-bench-object",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{BUCKET}/events.parquet"}],
            }
        ),
    )
    time.sleep(15)  # IAM propagation

    for lib in LIBS:
        for arch, lambda_arch in ARCHES.items():
            lam.create_function(
                FunctionName=fname(lib, arch),
                Runtime="python3.12",
                Role=role_arn,
                Handler=f"h_{lib}.handler",
                Code={"S3Bucket": BUCKET, "S3Key": f"code/{lib}-{arch}.zip"},
                Timeout=120,
                MemorySize=1024,
                Architectures=[lambda_arch],
                Environment={"Variables": {"BUCKET": BUCKET, "KEY": "events.parquet", "NONCE": "0"}},
            )
            print("created", fname(lib, arch))
    for lib in LIBS:
        for arch in ARCHES:
            lam.get_waiter("function_active_v2").wait(FunctionName=fname(lib, arch))
    print("all active")


def down():
    for lib in LIBS:
        for arch in ARCHES:
            name = fname(lib, arch)
            for call in (
                lambda: lam.delete_function(FunctionName=name),
                lambda: boto3.client("logs", region_name=REGION).delete_log_group(logGroupName=f"/aws/lambda/{name}"),
            ):
                try:
                    call()
                except Exception as e:  # already gone
                    print("skip:", e.__class__.__name__, name)
    try:
        iam.delete_role_policy(RoleName=ROLE, PolicyName="read-bench-object")
        iam.detach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        iam.delete_role(RoleName=ROLE)
    except Exception as e:
        print("skip role:", e)
    try:
        bucket = boto3.resource("s3", region_name=REGION).Bucket(BUCKET)
        bucket.objects.all().delete()
        bucket.delete()
    except Exception as e:
        print("skip bucket:", e)
    print("torn down")


if __name__ == "__main__":
    {"up": up, "down": down}[sys.argv[1]]()
