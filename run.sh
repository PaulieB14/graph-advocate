#!/bin/bash
cd "$(dirname "$0")"
set -a; source .env; set +a
source venv/bin/activate
python "$@"
