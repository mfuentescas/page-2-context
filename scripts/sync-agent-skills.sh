#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_SKILL="${ROOT_DIR}/agent-skill.md"

mkdir -p "${ROOT_DIR}/.github" "${ROOT_DIR}/.cursor/rules" "${ROOT_DIR}/.windsurf/rules"

for target in \
  "${ROOT_DIR}/.github/copilot-instructions.md" \
  "${ROOT_DIR}/.cursor/rules/page2context.md" \
  "${ROOT_DIR}/CLAUDE.md" \
  "${ROOT_DIR}/.windsurf/rules/page2context.md" \
  "${ROOT_DIR}/.clinerules"; do
  {
    printf '%s\n' "<!-- AUTO-GENERATED from agent-skill.md — do not edit directly. -->"
    printf '%s\n\n' "<!-- Run: ./scripts/sync-agent-skills.sh -->"
    cat "${AGENT_SKILL}"
  } > "${target}"
done

echo "Synced agent skill files to .github/.cursor/.windsurf/CLAUDE.md/.clinerules"

