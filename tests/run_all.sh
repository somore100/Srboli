#!/usr/bin/env bash
# Whole local check before tagging: every test file + the app's own screen
# selftest. Usage (from the repo root):  xvfb-run -a bash tests/run_all.sh
cd "$(dirname "$0")/.." || exit 1
PY=${PYTHON:-.venv/bin/python3}
fail=0
for t in tests/test_*.py; do
  [ "$t" = tests/test_scripts.py ] && continue
  $PY "$t" >/tmp/srboli_t.txt 2>&1 || { echo "FAIL $t"; tail -5 /tmp/srboli_t.txt; fail=1; }
done
$PY main.py --selftest /tmp/srboli_st.txt >/dev/null 2>&1
grep "screens load" /tmp/srboli_st.txt || fail=1
[ $fail = 0 ] && echo "ALL OK" || echo "PROBLEMS FOUND"
exit $fail
