#!/bin/sh
# Falla si un commit del rango trae atribución de un asistente.
# Uso: sh scripts/check-attribution.sh [rango]
#   sh scripts/check-attribution.sh origin/main..HEAD
#   sh scripts/check-attribution.sh            # último commit
set -eu

range="${1:--1}"

if ! git log "$range" --max-count=1 --format=%H >/dev/null 2>&1; then
  echo "check-attribution: rango inválido o no resoluble: '$range'" >&2
  exit 2
fi

pattern='co-authored-by:.*(claude|cursor|opencode|copilot|codex|anthropic|openai)|generated with .*(claude|cursor|opencode|copilot)|made-with:.*(cursor|claude|opencode)|harness:.*(opencode|cursor|claude)|(claude|cursor|opencode)-session:'

hits=$(git log "$range" --format='%H%n%s%n%b%n---' | grep -inE "$pattern" || true)

if [ -n "$hits" ]; then
  echo "check-attribution: hay atribución de un asistente en el historial del rango '$range':" >&2
  echo "$hits" >&2
  echo "" >&2
  echo "El autor es el humano. Reescribe el mensaje antes de publicar (git commit --amend o git rebase -i)." >&2
  exit 1
fi

echo "check-attribution: sin atribución de asistentes en '$range'."
exit 0
