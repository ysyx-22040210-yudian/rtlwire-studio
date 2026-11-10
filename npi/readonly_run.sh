#!/bin/bash
set -euo pipefail
mount --make-rprivate /
while IFS= read -r root; do
    [ -n "$root" ] || continue
    mount --bind "$root" "$root"
    mount -o remount,bind,ro "$root"
done < "$RTLWIRE_RO_ROOTS"
export LD_PRELOAD="$RTLWIRE_GUARD${LD_PRELOAD:+:$LD_PRELOAD}"
exec strace -f -qq -s 8192 -e trace=file,process -o "$RTLWIRE_AUDIT" \
    "$VERDI_HOME/bin/verdi" -batch -nologo \
    -play "$RTLWIRE_EXTRACTOR"
