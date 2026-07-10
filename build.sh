#!/usr/bin/env bash
# LazyUEFI build script
# Compile lazy_uefi.py into a standalone Linux executable using PyInstaller.

set -euo pipefail

APP_NAME="LazyUEFI"
SRC="lazy_uefi.py"

echo "==> Checking dependencies..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi

if ! python3 -m PyInstaller --version &>/dev/null; then
    echo "ERROR: PyInstaller not found. Install it with:"
    echo "  pip3 install pyinstaller"
    exit 1
fi

if ! command -v efibootmgr &>/dev/null; then
    echo "WARNING: efibootmgr is not installed on the build machine."
    echo "         The executable still works, but the target machine needs efibootmgr."
fi

echo "==> Cleaning previous builds..."
rm -rf build dist "${APP_NAME}.spec"

echo "==> Building ${APP_NAME}..."
python3 -m PyInstaller \
    --onefile \
    --windowed \
    --name "${APP_NAME}" \
    --clean \
    --noconfirm \
    "${SRC}"

echo "==> Build complete: dist/${APP_NAME}"
echo "    Run it with: ./dist/${APP_NAME}"
