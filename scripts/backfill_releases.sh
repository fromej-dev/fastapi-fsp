#!/usr/bin/env bash
# One-off: create GitHub Releases (and their tags) for versions that were published
# to PyPI before the release workflow created them. Each tag points at the commit
# that bumped pyproject.toml to that version; notes come from CHANGELOG.md.
#
# Run from the repo root with an authenticated GitHub CLI: scripts/backfill_releases.sh
# Pass --dry-run to print what would happen. Existing releases are skipped.
#
# Note: each new tag starts the release workflow as it existed at that old commit. Those
# runs fail at the PyPI upload because the files are already there; cancel or ignore
# them. Nothing is re-published.
set -euo pipefail

dry_run=false
[ "${1:-}" = "--dry-run" ] && dry_run=true

# version commit (0.2.3 was published to PyPI without a matching commit, so it is left out)
releases="
0.1.0 6965a8a
0.1.1 c4332f4
0.1.2 91a1c77
0.1.3 60f2d21
0.2.1 81b552d
0.2.2 0ded337
0.3.0 433952a
0.4.0 908e778
0.4.1 56407e0
0.4.2 5869e08
0.5.0 43343c5
0.5.1 7994b03
0.5.2 0286668
0.6.0 6e82339
"

latest="$(echo "$releases" | awk 'NF { v = $1 } END { print v }')"

echo "$releases" | while read -r version commit; do
  [ -z "$version" ] && continue
  tag="v$version"
  if gh release view "$tag" > /dev/null 2>&1; then
    echo "skip $tag (release exists)"
    continue
  fi
  sha="$(git rev-parse "$commit^{commit}")"
  notes="$(scripts/changelog_section.sh "$version")"
  latest_flag="--latest=false"
  [ "$version" = "$latest" ] && latest_flag="--latest"
  if $dry_run; then
    echo "would create $tag at $sha"
  else
    gh release create "$tag" --target "$sha" --title "$tag" --notes "$notes" "$latest_flag"
  fi
done
