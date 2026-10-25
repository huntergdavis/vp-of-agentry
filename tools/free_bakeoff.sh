#!/usr/bin/env bash
# Bake-off: the same decode task across several models, judged mechanically.
#
# Each run gets its own report, the citation gate, and the byte judge (which takes the file
# offset the BODY implies, so a model cannot pass by printing a plausible but wrong offset).
# The output is one table: model x body -> bytes verified yes/no, with wall time.
#
#   tools/free_bakeoff.sh "model1 model2" "OVL_0025_06AF OVL_0025_0136" [parallel]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${POOLRAD_REPO:-/home/hunter/workspace/poolrad-decomp}"
MODELS="${1:?usage: free_bakeoff.sh \"models\" \"bodies\" [parallel]}"
BODIES="${2:?bodies required}"
PAR="${3:-4}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
OUT="$HERE/data/bakeoff/$STAMP"
mkdir -p "$OUT"

PROMPT_FOR() { cat <<EOF
You are decoding one function in a DOS game decompilation repo at $REPO. The subject is $1 ($2).
Use the repo's own tools and files. Read-only: do not create, modify or delete any file.
Give me, in this order, and nothing else:
1. FILE OFFSET: the byte offset of this function inside resources/DOS/POOLRAD/GAME.OVR, showing the arithmetic.
2. BYTE DUMP: run a hexdump at that offset and paste its output verbatim (or an objdump-style listing whose leading column is the instruction bytes in hex), then the disassembly beside it.
3. SUMMARY: what it does, in one sentence.
4. EVIDENCE: repository paths you actually opened, only paths that exist.
If you cannot confirm something, write 'cannot confirm' and why. Keep it under 300 words.
EOF
}

run_one() {
  local model="$1" body="$2" off="$3" desc="$4"
  local safe; safe=$(echo "$model" | tr '/:' '__')
  local dir="$OUT/$safe"; mkdir -p "$dir"
  local rep="$dir/$body.md"
  local t0 t1
  t0=$(date +%s)
  ( cd "$REPO" && nice -n 15 timeout 600 pi -p -ne --model "$model" "$(PROMPT_FOR "$body" "$desc")" ) > "$rep" 2>"$dir/$body.err"
  t1=$(date +%s)
  local verdict="EMPTY"
  if [ -s "$rep" ]; then
    local bv
    bv=$(cd "$REPO" && python3 "$HERE/tools/free_body_check.py" "$rep" --expect-offset "$off" 2>&1 | tail -1)
    case "$bv" in
      *"BYTES MATCH"*) verdict="VERIFIED ($bv)" ;;
      *"BYTES DIFFER"*) verdict="DIFFERS ($bv)" ;;
      *"NO DUMP"*) verdict="NO DUMP" ;;
      *) verdict="UNCHECKED ($bv)" ;;
    esac
  fi
  printf '%s\t%s\t%s\t%ss\n' "$model" "$body" "$verdict" "$((t1-t0))" >> "$OUT/results.tsv"
  echo "done $model $body -> $verdict"
}

: > "$OUT/results.tsv"
jobs_run=0
for model in $MODELS; do
  for spec in $BODIES; do
    body="${spec%%:*}"; off="${spec##*:}"
    run_one "$model" "$body" "$off" "overlay body $body" &
    jobs_run=$((jobs_run+1))
    if [ $((jobs_run % PAR)) -eq 0 ]; then wait; fi
  done
done
wait

echo
echo "== bake-off $STAMP"
column -t -s $'\t' "$OUT/results.tsv" 2>/dev/null || cat "$OUT/results.tsv"
echo
echo "verified runs / total by model:"
awk -F'\t' '{tot[$1]++; if ($3 ~ /^VERIFIED/) ok[$1]++} END {for (m in tot) printf "  %-46s %d/%d\n", m, ok[m]+0, tot[m]}' "$OUT/results.tsv" | sort
echo "results in $OUT/results.tsv"
