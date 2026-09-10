#!/usr/bin/env bash
# Render build script for the Parakh backend.
#
# Installs core dependencies first (always succeeds), then attempts to install
# the ML/OCR dependencies. If the ML install fails (e.g. no compatible wheel
# for the current Python version), the backend still starts and returns
# PENDING_ML for inspection processing until the environment is fixed.
#
# Set SKIP_ML_DEPS=1 as a Render environment variable to skip the ML install
# entirely (useful for fast redeploys when only non-ML code changed).

set -e  # Exit immediately on any error from the core install

echo "==> Installing core dependencies..."
pip install -r requirements.txt

echo "==> Core dependencies installed successfully."

if [ "${SKIP_ML_DEPS}" = "1" ]; then
    echo "==> SKIP_ML_DEPS=1 — skipping ML dependency install."
    exit 0
fi

echo "==> Installing ML/OCR dependencies (paddlepaddle, paddleocr, opencv)..."
# Use || true so a failure here does NOT abort the build.
# The backend handles missing ML packages via MLNotIntegratedError.
pip install -r requirements-ml.txt || {
    echo "WARNING: ML dependencies could not be installed."
    echo "  The backend will start but POST /api/inspections/{id}/process"
    echo "  will return PENDING_ML until ML packages are available."
    echo "  Ensure Python 3.10.x is used (PaddlePaddle requires Python <=3.12)."
}

echo "==> Build complete."
