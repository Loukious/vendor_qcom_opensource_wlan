#!/usr/bin/env bash
# Prepare a kernel-ABI tree for building qca_cld3_wcn7750.ko against the
# Kono-Ha GKI kernel that actually boots on onyx.
#
# The ROM tree's own kernel (kernel/xiaomi/sm8735, 6.6.82) produces a module
# whose probe fails with -EPERM on the Kono-Ha 6.6.143 GKI kernel. The module
# that works is built the way the konoha-kernel-gki workflow does it:
#
#   - MiCode onyx-v-oss source (6.6.56) with VERSION/PATCHLEVEL/SUBLEVEL
#     stamped to the Kono-Ha release and LOCALVERSION=-android15-8-4k
#   - gki_defconfig + sun_perf.config + onyx_perf.config, modules_prepare only
#   - Module.symvers from the Kono-Ha wlan-kernel-symbols release
#
# Usage (env overrides everything):
#   KONOHA_ABI_DIR   output dir (default: kernel/xiaomi/konoha-abi relative to
#                    the built tree; set it explicitly when running from the
#                    onyx-wlan fork checkout, which has different depth)
#   KONOHA_SYMVERS   path to the Kono-Ha Module.symvers (downloaded if unset)
#   SYMVERS_URL      override the release URL (per-kernel-release symvers
#                    assets; a URL change re-downloads even when a cached
#                    Module.symvers is present -- see .symvers-url)
#   CLANG_PATH       clang bin dir (default: /usr/lib/llvm-*/bin with PATH fallback)
#   --check-only     validate prepared cache offline (used by the ROM Makefile)
#
# Idempotent: skips everything when the stamp file matches.
set -euo pipefail

CHECK_ONLY=0
case "${1:-}" in
    '') ;;
    --check-only) CHECK_ONLY=1 ;;
    *) echo "Usage: $0 [--check-only]" >&2; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WLAN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Default cache: kernel/xiaomi/konoha-abi -- four levels above the wlan dir of
# the built tree (kernel/xiaomi/sm8735-modules/qcom/opensource/wlan), i.e.
# outside every git project so repo syncs and the apply.sh rsync overlay never
# touch it. Set KONOHA_ABI_DIR when running from somewhere with different
# depth (e.g. the onyx-wlan fork checkout, where the wlan dir is two levels
# shallower).
ABI_DIR="${KONOHA_ABI_DIR:-$(cd "$WLAN_DIR/../../../.." && pwd)/konoha-abi}"
SRC_DIR="$ABI_DIR/src"
OUT_DIR="$ABI_DIR/out"
STAMP="$ABI_DIR/.prepared"

KERNEL_SOURCE_REPO="${KERNEL_SOURCE_REPO:-https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git}"
KERNEL_SOURCE_BRANCH="${KERNEL_SOURCE_BRANCH:-onyx-v-oss}"
KONOHA_KERNEL_RELEASE="${KONOHA_KERNEL_RELEASE:-6.6.57-android15-8-4k}"
SYMVERS_URL="${SYMVERS_URL:-https://github.com/Loukious/konoha-kernel-gki/releases/download/wlan-kernel-symbols/Module.symvers}"
# File-based pin survives Android's ninja environment filtering. Do not source
# shell code here: this is one literal URL written by the pre-build recipe.
if [[ -s "$ABI_DIR/.symvers-pin" ]]; then
	SYMVERS_URL="$(cat "$ABI_DIR/.symvers-pin")"
elif [[ "$CHECK_ONLY" == 1 ]]; then
	echo "FATAL: missing ABI release pin; run CI ABI preparation before mka" >&2
	exit 1
fi
SYMVERS_SHA256_URL="${SYMVERS_URL}.sha256"

KERNEL_DEVICE="${KERNEL_SOURCE_BRANCH%%-*}"   # onyx
KERNEL_LOCALVERSION="-${KONOHA_KERNEL_RELEASE#*-}"   # -android15-8-4k
BASE_VERSION="${KONOHA_KERNEL_RELEASE%%-*}"   # 6.6.57
IFS=. read -r KERNEL_VERSION KERNEL_PATCHLEVEL KERNEL_SUBLEVEL <<< "$BASE_VERSION"

STAMP_PAYLOAD="$KERNEL_SOURCE_REPO $KERNEL_SOURCE_BRANCH $KONOHA_KERNEL_RELEASE $SYMVERS_URL"
cache_ok() {
	[[ -f "$STAMP" && "$(cat "$STAMP")" == "$STAMP_PAYLOAD" \
		&& -d "$SRC_DIR" && -s "$OUT_DIR/Module.symvers" \
		&& -f "$OUT_DIR/include/config/kernel.release" \
		&& "$(cat "$OUT_DIR/include/config/kernel.release")" == "$KONOHA_KERNEL_RELEASE" \
		&& -s "$ABI_DIR/.prepared-symvers-sha256" ]] || return 1
	[[ "$(sha256sum "$OUT_DIR/Module.symvers")" == "$(cat "$ABI_DIR/.prepared-symvers-sha256")" ]]
}

# Idempotent: skips everything when the stamp file matches AND the prepared
# output is still intact (the stamp alone is not enough -- out/ may have been
# removed since).
if cache_ok; then
	echo "[konoha-abi] already prepared: $ABI_DIR"
	echo "[konoha-abi] kernel release: $(cat "$OUT_DIR/include/config/kernel.release")"
	exit 0
fi
if [[ "$CHECK_ONLY" == 1 ]]; then
	echo "FATAL: ABI cache missing, stale or corrupt; prepare it before mka (no downloads during compilation)" >&2
	exit 1
fi

# --- toolchain -------------------------------------------------------------
if [[ -n "${CLANG_PATH:-}" ]]; then
	export PATH="$CLANG_PATH:$PATH"
fi
if ! command -v clang >/dev/null 2>&1; then
	for d in /usr/lib/llvm-*/bin; do [[ -x "$d/clang" ]] && export PATH="$d:$PATH" && break; done
fi
command -v clang >/dev/null 2>&1 || { echo "clang not found" >&2; exit 1; }
command -v perl >/dev/null 2>&1 || { echo "perl not found (needed for Makefile stamping)" >&2; exit 1; }

# --- Module.symvers --------------------------------------------------------
mkdir -p "$ABI_DIR"
SYMVERS="${KONOHA_SYMVERS:-$ABI_DIR/Module.symvers}"
# (Re)fetch when the file is missing OR when it was cached from a different
# URL. The stamp above already re-prepares everything when SYMVERS_URL
# changes, but the cached file itself survived that path -- a persistent
# workspace (crave) would silently build the module against stale symbols.
# .symvers-url records where the current file came from. KONOHA_SYMVERS (an
# explicit local file) is always taken as-is.
cached_url="$(cat "$ABI_DIR/.symvers-url" 2>/dev/null || true)"
if [[ ! -f "$SYMVERS" ]] || \
		[[ -z "${KONOHA_SYMVERS:-}" && "$cached_url" != "$SYMVERS_URL" ]]; then
	if [[ -n "$cached_url" && "$cached_url" != "$SYMVERS_URL" ]]; then
		echo "[konoha-abi] cached Module.symvers is from a different URL -- re-fetching"
		echo "[konoha-abi]   cached: $cached_url"
		echo "[konoha-abi]   wanted: $SYMVERS_URL"
	else
		echo "[konoha-abi] fetching Kono-Ha Module.symvers"
	fi
	# Verify in scratch before replacing a previously good cached file.
	tmp_symvers="$(mktemp -d "$ABI_DIR/.symvers-download.XXXXXX")"
	trap 'rm -rf "$tmp_symvers"' EXIT
	curl -fL --retry 3 "$SYMVERS_URL" -o "$tmp_symvers/Module.symvers"
	curl -fsL --retry 3 "$SYMVERS_SHA256_URL" -o "$tmp_symvers/Module.symvers.sha256"
	(cd "$tmp_symvers" && sha256sum -c Module.symvers.sha256)
	mv "$tmp_symvers/Module.symvers" "$SYMVERS"
	mv "$tmp_symvers/Module.symvers.sha256" "$SYMVERS.sha256"
	printf '%s\n' "$SYMVERS_URL" > "$ABI_DIR/.symvers-url"
fi
[[ -s "$SYMVERS" ]] || { echo "Module.symvers is missing or empty" >&2; exit 1; }
if [[ -z "${KONOHA_SYMVERS:-}" ]]; then
	[[ -s "$SYMVERS.sha256" ]] || { echo "Missing Module.symvers checksum" >&2; exit 1; }
	(cd "$ABI_DIR" && sha256sum -c "$(basename "$SYMVERS").sha256")
fi

# --- source ----------------------------------------------------------------
if [[ ! -d "$SRC_DIR/.git" ]]; then
	rm -rf "$SRC_DIR"
	echo "[konoha-abi] cloning $KERNEL_SOURCE_REPO @ $KERNEL_SOURCE_BRANCH"
	git clone --depth=1 --filter=blob:none --single-branch \
		--branch "$KERNEL_SOURCE_BRANCH" "$KERNEL_SOURCE_REPO" "$SRC_DIR"
fi
git -C "$SRC_DIR" fetch --depth=1 origin "$KERNEL_SOURCE_BRANCH" 2>/dev/null || true
git -C "$SRC_DIR" checkout --detach FETCH_HEAD 2>/dev/null || \
	git -C "$SRC_DIR" checkout --detach "origin/$KERNEL_SOURCE_BRANCH"

# --- stamp release + vendor stubs ------------------------------------------
export KERNEL_VERSION KERNEL_PATCHLEVEL KERNEL_SUBLEVEL
perl -0pi -e '
	s/^VERSION = .*/VERSION = $ENV{KERNEL_VERSION}/m;
	s/^PATCHLEVEL = .*/PATCHLEVEL = $ENV{KERNEL_PATCHLEVEL}/m;
	s/^SUBLEVEL = .*/SUBLEVEL = $ENV{KERNEL_SUBLEVEL}/m;
' "$SRC_DIR/Makefile"

STUBS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/konoha-abi-stubs"
install -D -m 0644 "$STUBS_DIR/drivers/misc/hwid/Kconfig" \
	"$SRC_DIR/drivers/misc/hwid/Kconfig"
install -D -m 0644 "$STUBS_DIR/include/hwid.h" \
	"$SRC_DIR/include/hwid.h"
rm -rf "$SRC_DIR/drivers/power/supply/mca"
install -D -m 0644 "$STUBS_DIR/drivers/power/supply/mca/Kconfig" \
	"$SRC_DIR/drivers/power/supply/mca/Kconfig"

VENDOR_PERF_CONFIG="$SRC_DIR/arch/arm64/configs/vendor/${KERNEL_DEVICE}_perf.config"
[[ -f "$VENDOR_PERF_CONFIG" ]] || { echo "Missing vendor perf config: $VENDOR_PERF_CONFIG" >&2; exit 1; }

# --- configure + modules_prepare -------------------------------------------
echo "[konoha-abi] configuring $KERNEL_DEVICE ABI kernel ($KONOHA_KERNEL_RELEASE)"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
KCONFIG_CONFIG="$OUT_DIR/.config" \
	"$SRC_DIR/scripts/kconfig/merge_config.sh" -m -r -y \
	"$SRC_DIR/arch/arm64/configs/gki_defconfig" \
	"$SRC_DIR/arch/arm64/configs/vendor/sun_perf.config" \
	"$VENDOR_PERF_CONFIG"
"$SRC_DIR/scripts/config" --file "$OUT_DIR/.config" \
	--set-str LOCALVERSION "$KERNEL_LOCALVERSION" \
	--disable LOCALVERSION_AUTO \
	--disable KUNIT
make -j"$(nproc)" -C "$SRC_DIR" O="$OUT_DIR" \
	ARCH=arm64 LLVM=1 LLVM_IAS=1 LOCALVERSION= \
	olddefconfig prepare modules_prepare
cp "$SYMVERS" "$OUT_DIR/Module.symvers"

kernel_release="$(cat "$OUT_DIR/include/config/kernel.release")"
if [[ "$kernel_release" != "$KONOHA_KERNEL_RELEASE" ]]; then
	echo "Kernel release mismatch: got '$kernel_release', want '$KONOHA_KERNEL_RELEASE'" >&2
	exit 1
fi

printf '%s' "$STAMP_PAYLOAD" > "$STAMP"
sha256sum "$OUT_DIR/Module.symvers" > "$ABI_DIR/.prepared-symvers-sha256"
echo "[konoha-abi] prepared: $ABI_DIR (release $kernel_release)"
