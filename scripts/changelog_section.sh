#!/usr/bin/env bash
# Print the CHANGELOG.md section for one version, e.g. `scripts/changelog_section.sh 0.6.0`.
# Used by the release workflow for GitHub Release notes. Exits 1 if the section is missing.
set -euo pipefail

version="${1:?usage: $0 <version>}"
changelog="${2:-CHANGELOG.md}"

notes="$(awk -v v="$version" '
  index($0, "## [" v "]") == 1 { found = 1; next }
  found && /^## \[/ { exit }
  found { print }
' "$changelog")"

if [ -z "${notes//[[:space:]]/}" ]; then
  echo "No section for version $version in $changelog" >&2
  exit 1
fi
printf '%s\n' "$notes"
