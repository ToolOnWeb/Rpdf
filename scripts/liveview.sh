#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PDF_CONTROL_ROOT="$ROOT"
export MIX_HOME="$ROOT/.runtime/mix"
export HEX_HOME="$ROOT/.runtime/hex"
export XDG_CACHE_HOME="$ROOT/.runtime/cache"
export HEX_CACERTS_PATH=/etc/ssl/certs/ca-certificates.crt
export PATH="$ROOT/.runtime/elixir/installs/otp/27.3.4.2/bin:$ROOT/.runtime/elixir/installs/elixir/1.18.4-otp-27/bin:$PATH"
if [ -f "$ROOT/.runtime/tessdata/ara.traineddata" ]; then
  export TESSDATA_PREFIX="${TESSDATA_PREFIX:-$ROOT/.runtime/tessdata}"
fi
cd "$ROOT/web"
exec mix "$@"
