#!/usr/bin/env bash
# System packages for a fresh Ubuntu 24.04 box (any cloud or bare metal): compiler, git,
# pigz, util-linux (taskset) + util-linux-extra (fincore), and Python 3.14 from the deadsnakes PPA.
set -euo pipefail
sudo apt-get update -y -q >/dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q build-essential git pigz wget curl \
    util-linux util-linux-extra software-properties-common >/dev/null
sudo add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1
sudo apt-get update -y -q >/dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3.14 python3.14-venv >/dev/null
g++ --version | head -1; python3.14 --version
