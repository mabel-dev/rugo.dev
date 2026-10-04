#!/usr/bin/env bash
# Python environment for the Opteryx and rugo drivers: opteryx-core from PyPI (rugo ships in
# the same wheel). Needs Python 3.14 (standard GIL build): PYTHON=/path/to/python3.14.
set -euo pipefail
cd "$(dirname "$0")"
source versions.env
${PYTHON:-python$PYTHON_VERSION} -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q "opteryx-core==$OPTERYX_VERSION"
.venv/bin/python -c "import sys, opteryx, rugo; print('python', sys.version.split()[0], '| opteryx', opteryx.__version__, '| rugo', rugo.__version__)"
