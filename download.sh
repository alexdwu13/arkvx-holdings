#!/bin/bash
# Download ARK Venture Fund (ARKVX) daily holdings CSV

set -euo pipefail

DATA_DIR="$(dirname "$0")/data"
URL="https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_VENTURE_FUND_ARKVX_HOLDINGS.csv"
DATE=$(date +%Y-%m-%d)
OUTFILE="${DATA_DIR}/ARKVX_HOLDINGS_${DATE}.csv"

if [ -f "$OUTFILE" ]; then
    echo "Already downloaded today: $OUTFILE"
    exit 0
fi

curl -fsSL -o "$OUTFILE" "$URL"
echo "Downloaded: $OUTFILE"
