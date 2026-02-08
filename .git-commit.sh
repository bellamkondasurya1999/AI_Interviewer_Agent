#!/usr/bin/env bash
set -e

cd "/c/Users/bella/Downloads/AI Interview Agent"
git add .
git commit -m "$(cat <<'EOF'
Add Firebase auth, storage, and hosting setup.

This integrates Firebase authentication and resume persistence, updates UI branding to Sura, and adds Firebase Hosting configuration while cleaning up unused test/scripts.
EOF
)"
git status -sb
