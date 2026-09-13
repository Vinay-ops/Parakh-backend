#!/usr/bin/env bash
# Render build script for the Parakh backend.
#
# Installs core dependencies first (always succeeds), then attempts to install
# the ML/OCR dependencies. If the ML install fails, the backend still starts
# and returns PENDING_ML for inspection processing until the environment is
# fixed.
#
# Set SKIP_ML_DEPS=1 as a Render environment variable to skip the ML install
# entirely (useful for fast redeploys when only non-ML code changed).
#
# Python version is pinned via the PYTHON_VERSION env var in render.yaml
# (highest precedence) and mirrored in .python-version (second precedence).
# PaddlePaddle 3.x supports Python 3.9–3.13; we pin 3.12.10.

set -e  # Exit immediately on any error from the core install

echo "==> Python version in use:"
python --version

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
if pip install -r requirements-ml.txt; then
    echo "==> ML dependencies installed successfully."
    # Confirm the key packages are importable — a failed import here means
    # the build log will surface the real error rather than a silent boot-time
    # failure.
    python -c "import paddle; print('paddle version:', paddle.__version__)"
    python -c "import cv2; print('cv2 version:', cv2.__version__)"
    echo "==> ML/OCR packages verified importable."
else
    echo "WARNING: ML dependencies could not be installed."
    echo "  The backend will start but POST /api/inspections/{id}/process"
    echo "  will return PENDING_ML until ML packages are available."
    echo "  Python version: $(python --version)"
    echo "  PYTHON_VERSION env: ${PYTHON_VERSION:-not set}"
fi

echo "==> Build complete."
