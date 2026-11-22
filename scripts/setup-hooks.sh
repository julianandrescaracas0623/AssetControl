#!/bin/sh
# Instala los hooks versionados en .git/hooks/.
# Uso: sh scripts/setup-hooks.sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
hooks_dir=$(git rev-parse --git-path hooks)
src="$repo_root/scripts/hooks"

install -m 755 "$src/pre-commit" "$hooks_dir/pre-commit"
install -m 755 "$src/commit-msg" "$hooks_dir/commit-msg"

echo "Hooks instalados en $hooks_dir"
echo "  - pre-commit: bloquea publicar los archivos locales del arnés"
echo "  - commit-msg: elimina la atribución de IA del mensaje"
