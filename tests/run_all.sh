#!/usr/bin/env bash
# Tüm örnek karneleri işler; herhangi birinde doğrulama SORUN VAR ise hata verir.
set -e
cd "$(dirname "$0")/.."
fail=0
for f in samples/*.pdf; do
  out=$(python3 cli.py "$f" --out out/)
  echo "$out"
  echo "$out" | grep -q "doğrulama: TAMAM" || fail=1
done
exit $fail
