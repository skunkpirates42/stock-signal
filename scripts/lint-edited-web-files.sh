#!/bin/sh
input=$(cat)
cwd=$(printf "%s" "$input" | jq -r '.cwd')
repo=$(git -C "$cwd" rev-parse --show-toplevel) || exit 0

edited=$(printf "%s" "$input" | jq -r '.tool_input.command // empty' |
  sed -nE 's/^\*\*\* (Add File|Update File|Move to): //p' |
  while read -r path; do
    case "$path" in (/*) echo "$path" ;; (*) echo "$cwd/$path" ;; esac
  done |
  grep "^$repo/web/" | while read -r path; do [ -f "$path" ] && echo "$path"; done)
[ -z "$edited" ] && exit 0

cd "$repo/web" || exit 0
echo "$edited" | xargs pnpm exec prettier --write --ignore-unknown >/dev/null 2>&1

# ESLint errors go back to Codex as feedback (exit 2) so it fixes them in the same turn.
lintable=$(echo "$edited" | grep -E '\.(js|jsx|mjs|cjs|ts|tsx)$')
[ -z "$lintable" ] && exit 0
lint_output=$(echo "$lintable" | xargs pnpm exec eslint 2>&1) && exit 0
echo "$lint_output" >&2
exit 2
