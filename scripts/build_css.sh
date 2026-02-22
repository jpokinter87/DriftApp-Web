#!/bin/bash
# Build Tailwind CSS for DriftApp
# Usage:
#   ./scripts/build_css.sh          # One-time build (minified)
#   ./scripts/build_css.sh --watch  # Watch mode for development

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TAILWIND="$PROJECT_ROOT/tailwindcss"
INPUT="$PROJECT_ROOT/web/static/css/tailwind-input.css"
OUTPUT="$PROJECT_ROOT/web/static/css/tailwind-output.css"

if [ ! -f "$TAILWIND" ]; then
    echo "Error: tailwindcss binary not found at $TAILWIND"
    echo "Download it: curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64"
    exit 1
fi

if [ "$1" = "--watch" ]; then
    echo "Tailwind CSS watch mode started..."
    echo "Input:  $INPUT"
    echo "Output: $OUTPUT"
    "$TAILWIND" -i "$INPUT" -o "$OUTPUT" --watch
else
    echo "Building Tailwind CSS..."
    "$TAILWIND" -i "$INPUT" -o "$OUTPUT" --minify
    echo "Done: $OUTPUT ($(wc -c < "$OUTPUT") bytes)"
fi
