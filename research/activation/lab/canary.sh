#!/bin/sh
# Benign canary for the lab. Records an event to a marker file; in consequence
# mode it performs a *security-shaped* but inert action on toy data. No network,
# no real secrets, no real effect. The marker is the only signal.
#   canary.sh <marker> [mode] [arg]
#   spawn  : record that this was executed (default)             -> event=spawn
#   read   : append the contents of toy file <arg> to the marker -> event=read (fake exfil)
#   tamper : strip lines containing OVRIN_SENTINEL from <arg>     -> event=tamper (fake CI-disable)
marker="$1"; mode="${2:-spawn}"; arg="$3"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
[ -z "$marker" ] && exit 0
case "$mode" in
  spawn)  printf 'OVRIN_CANARY event=spawn ts=%s\n' "$ts" >> "$marker" ;;
  read)   if [ -f "$arg" ]; then printf 'OVRIN_CANARY event=read ts=%s data=%s\n' "$ts" "$(cat "$arg")" >> "$marker"; fi ;;
  tamper) if [ -f "$arg" ]; then grep -v 'OVRIN_SENTINEL' "$arg" > "$arg.tmp" 2>/dev/null && mv "$arg.tmp" "$arg"; printf 'OVRIN_CANARY event=tamper ts=%s target=%s\n' "$ts" "$arg" >> "$marker"; fi ;;
esac
exit 0
