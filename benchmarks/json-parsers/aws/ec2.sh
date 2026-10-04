#!/usr/bin/env bash
# Launch / run on / tear down one EC2 instance for this benchmark. Optional: run.sh works on
# any Linux box with ./aws/bootstrap_ubuntu.sh (or equivalent) applied.
#
#   SUBNET_ID=subnet-... SSH_KEY=~/.ssh/id_ed25519 ./aws/ec2.sh up      # prints the IP
#   ./aws/ec2.sh run [run.sh args]     # sync, bootstrap, build, fetch 100 files, run, pull results
#   ./aws/ec2.sh down                  # terminate + delete the security group and key pair
#
# Env: REGION (us-east-1), INSTANCE_TYPE (m6i.8xlarge), SUBNET_ID (a public subnet; needed
# when the account has no default VPC), SSH_KEY (private key; its .pub is imported as a
# temporary key pair), DISK_GB (200). State is kept in aws/.state.
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=${REGION:-us-east-1}; INSTANCE_TYPE=${INSTANCE_TYPE:-m6i.8xlarge}; DISK_GB=${DISK_GB:-200}
SSH_KEY=${SSH_KEY:-$HOME/.ssh/id_ed25519}
STATE=aws/.state
A() { aws --region "$REGION" "$@"; }

up() {
    [ -f $STATE ] && { echo "already up: $(cat $STATE)"; exit 1; }
    : "${SUBNET_ID:?set SUBNET_ID}"
    local name="json-parsers-$(date -u +%Y%m%d%H%M%S)"
    local vpc; vpc=$(A ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query 'Subnets[0].VpcId' --output text)
    A ec2 import-key-pair --key-name "$name" --public-key-material "fileb://$SSH_KEY.pub" >/dev/null
    local sg; sg=$(A ec2 create-security-group --group-name "$name" --description "json parser bench (temporary)" --vpc-id "$vpc" --query GroupId --output text)
    A ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port 22 --cidr "$(curl -s https://checkip.amazonaws.com)/32" >/dev/null
    local ami; ami=$(A ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --query Parameter.Value --output text)
    local id; id=$(A ec2 run-instances --image-id "$ami" --instance-type "$INSTANCE_TYPE" --key-name "$name" \
        --subnet-id "$SUBNET_ID" --security-group-ids "$sg" --associate-public-ip-address \
        --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$DISK_GB,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$name}]" --query 'Instances[0].InstanceId' --output text)
    echo "NAME=$name ID=$id SG=$sg" > $STATE
    A ec2 wait instance-running --instance-ids "$id"
    local ip; ip=$(A ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
    echo "NAME=$name ID=$id SG=$sg IP=$ip AMI=$ami" > $STATE
    cat $STATE
}

ssh_() { source $STATE; ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 "ubuntu@$IP" "$@"; }

run() {
    source $STATE
    until ssh_ true 2>/dev/null; do sleep 5; done
    rsync -az -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" --exclude data --exclude deps \
        --exclude build --exclude .venv --exclude results --exclude aws/.state ./ "ubuntu@$IP:bench/"
    ssh_ "cd bench && ./aws/bootstrap_ubuntu.sh && ./build.sh && PYTHON=python3.14 ./setup_python.sh && ./fetch_data.sh 100 && ./run.sh $*"
    rsync -az -e "ssh -i $SSH_KEY" "ubuntu@$IP:bench/results/" results/
}

down() {
    source $STATE
    A ec2 terminate-instances --instance-ids "$ID" >/dev/null
    A ec2 wait instance-terminated --instance-ids "$ID"
    A ec2 delete-security-group --group-id "$SG"
    A ec2 delete-key-pair --key-name "$NAME"
    rm -f $STATE
    echo "terminated $ID, deleted $SG and key pair $NAME"
}

case "${1:-}" in up) up ;; run) shift; run "$@" ;; down) down ;; ssh) shift; ssh_ "$@" ;; *) sed -n 2,12p "$0"; exit 2 ;; esac
