#!/usr/bin/env bash
# ============================================================
# DocFlow – Release Script
# ============================================================
# Usage: ./scripts/release.sh [patch|minor|major]
# Creates a git tag and pushes it to trigger the release workflow.
# ============================================================

set -euo pipefail

BUMP_TYPE="${1:-patch}"

# Get current version from git tags
CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
CURRENT_VERSION="${CURRENT_TAG#v}"

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

case "$BUMP_TYPE" in
  patch) PATCH=$((PATCH + 1)) ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  *)
    echo "Usage: $0 [patch|minor|major]"
    exit 1
    ;;
esac

NEW_VERSION="v${MAJOR}.${MINOR}.${PATCH}"

echo "Current version: ${CURRENT_TAG}"
echo "New version:     ${NEW_VERSION}"
echo ""

read -p "Create tag ${NEW_VERSION} and push? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  git tag -a "${NEW_VERSION}" -m "Release ${NEW_VERSION}"
  git push origin "${NEW_VERSION}"
  echo ""
  echo "Tag ${NEW_VERSION} pushed. GitHub Actions will create the release."
else
  echo "Aborted."
fi
