#!/usr/bin/env bash
#
# Syntax-check every shell script in the project, each with the shell that
# will run it.
#
# "bash -n one two" checks only "one": the rest are taken as its arguments.
# CI was written that way at first, and for that reason never looked at
# build-deb.sh or postinst. A broken postinst breaks the installation of the
# package, so the scripts are checked one at a time, and the list lives here
# and nowhere else.

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

bash_scripts=(t48-programmer packaging/*.sh)
sh_scripts=(
    packaging/t48-programmer
    packaging/postinst
    packaging/postrm
    packaging/install-update
)

for script in "${bash_scripts[@]}"; do
    bash -n "${script}"
    echo "bash  ${script}"
done
for script in "${sh_scripts[@]}"; do
    sh -n "${script}"
    echo "sh    ${script}"
done
