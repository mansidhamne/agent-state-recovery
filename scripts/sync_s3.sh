#!/usr/bin/env bash
# Usage: scripts/sync_s3.sh <bucket>
set -euo pipefail

aws s3 sync runs/ "s3://${1:?bucket name required}/runs/"
