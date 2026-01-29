#!/bin/bash
# Run Artifactory Sync Tool using uv

# Ensure we're in the project directory
cd "$(dirname "$0")" || exit 1

# Run with uv
uv run artifactory-sync "$@"
