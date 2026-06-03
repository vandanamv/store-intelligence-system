#!/bin/bash
# Apex Store Intelligence - Detection Pipeline Execution Script

# Exit immediately if a command exits with a non-zero status
set -e

# Default parameters
STORE_ID="STORE_BLR_002"
API_URL="http://localhost:8000/events/ingest"
DURATION=60

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --store) STORE_ID="$2"; shift ;;
        --url) API_URL="$2"; shift ;;
        --duration) DURATION="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "[*] Launching Store Analytics Detection Engine..."
echo "[*] Target Store: $STORE_ID"
echo "[*] Ingestion URL: $API_URL"
echo "[*] Running for $DURATION seconds..."

# Set Python path to ensure module imports resolve correctly
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Execute the main pipeline script
python pipeline/detect.py --store "$STORE_ID" --url "$API_URL" --duration "$DURATION"

echo "[*] Pipeline finished processing."
