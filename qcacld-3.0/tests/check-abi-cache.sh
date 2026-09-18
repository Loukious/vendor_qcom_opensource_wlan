#!/usr/bin/env bash
# Small offline regression test; no source checkout or toolchain needed.
set -euo pipefail
prep="$(cd "$(dirname "$0")/.." && pwd)/konoha-abi-prep.sh"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
abi="$fixture/abi"
mkdir -p "$abi/src" "$abi/out/include/config" "$fixture/bin"
url='https://github.com/Loukious/konoha-kernel-gki/releases/download/test-latest/Module.symvers'
printf '%s\n' "$url" > "$abi/.symvers-pin"
printf '%s' "https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git onyx-v-oss 6.6.57-android15-8-4k $url" > "$abi/.prepared"
printf '%s\n' '6.6.57-android15-8-4k' > "$abi/out/include/config/kernel.release"
printf '%s\n' '0x12345678 test_symbol vmlinux EXPORT_SYMBOL' > "$abi/out/Module.symvers"
sha256sum "$abi/out/Module.symvers" > "$abi/.prepared-symvers-sha256"
# Fail visibly if validation ever tries network or a build tool.
for tool in curl git make clang perl; do
    printf '#!/bin/sh\necho forbidden-tool >> "%s"\nexit 99\n' "$fixture/tools-used" > "$fixture/bin/$tool"
    chmod +x "$fixture/bin/$tool"
done
check() {
    env -i PATH="$fixture/bin:/usr/bin:/bin" KONOHA_ABI_DIR="$abi" bash "$prep" --check-only
}
reject() {
    if check; then echo 'Expected cache rejection' >&2; exit 1; fi
    [[ ! -e "$fixture/tools-used" ]]
}
check
printf '%s\n' "$url-stale" > "$abi/.symvers-pin"
reject
printf '%s\n' "$url" > "$abi/.symvers-pin"
printf '%s\n' corrupted >> "$abi/out/Module.symvers"
reject
sha256sum "$abi/out/Module.symvers" > "$abi/.prepared-symvers-sha256"
printf '%s\n' wrong-release > "$abi/out/include/config/kernel.release"
reject
printf '%s\n' '6.6.57-android15-8-4k' > "$abi/out/include/config/kernel.release"
rm "$abi/.prepared-symvers-sha256"
reject
rm "$abi/.symvers-pin"
reject
[[ ! -e "$fixture/tools-used" ]]
echo 'PASS: filtered environment, release pin, stale/corrupt/missing cache; no network/build tools'
