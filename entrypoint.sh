#!/bin/sh

export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus/metrics}"
if [ -d "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -rf "$PROMETHEUS_MULTIPROC_DIR"
fi
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

python run.py
