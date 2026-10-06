#!/usr/bin/env bash
# UndoAtlas live demo. Run from anywhere:  bash ~/cawe-push/scripts/demo_run.sh
# Live parts write only under runs/*_demo_<time>/. Recorded episodes, HARs and grid data are never touched;
# step 5 rewrites its own derived summaries in out/ (k3/k16-k19 json, fig_grid.tex, tab_calib.tex) with identical values.
set -u
cd "$(dirname "$0")/.."
PY="${PY:-./.venv312/bin/python}"   # Python 3.12 env from requirements-py312.txt (browsergym, playwright, webarena-verified)
STAMP=$(date +%H%M%S)
export PYTHONPATH=. PYTHONWARNINGS=ignore
quiet() { grep -v --line-buffered -E 'beartype|warn\(|Overriding the task|axtree. Retrying|Execution context was destroyed|^\s*$'; }
h()     { printf "\n\033[1;36m== %s ==\033[0m\n" "$*"; }
pause() { printf "\n\033[2m[Enter] next step\033[0m "; read -r _; }

h "0. Preflight"
docker version --format 'Docker engine {{.Server.Version}} is running' || { echo "Start Docker Desktop first."; exit 1; }
"$PY" -c "import browsergym, playwright, webarena_verified; print('Python env OK')"

h "1. Code map"
cat <<'MAP'
cawebagent/trace/runner.py     instrumented episode runner: browser + HAR capture + phase timestamps  (FR1, FR2)
cawebagent/trace/reset.py      true reset: destroy the container and recreate it from the image        (FR1)
cawebagent/trace/har_parse.py  HAR -> write events, phase split, collateral detection                  (FR6-FR8)
cawebagent/agent/, lm/         the LLM agent under audit and its effort-controlled model layer        (FR3, FR23)
scripts/30_e1_grid.py          reversibility probe: drive state, act, find inverse, TAKE it, read back (FR4, FR13-FR17)
scripts/39_e2_grid_postmill.py the same probe on a second application (Postmill forum)
scripts/37_*.py, exp0b_*.py    benchmark audit: 8 of 663 checks can say "this should not happen"     (FR11)
scripts/31,33,38,41_*.py       re-derive every reported number and FAIL if it drifts                  (FR26)
tests/test_separation.py       detector may not import the risk rules                                 (NFR3)
MAP
pause

h "2. Test: the change detector cannot see the risk rules (NFR3)"
"$PY" tests/test_separation.py
pause

h "3. LIVE: same official score, different damage (collateral detector, ~2 min)"
echo "Arm A cancels order 302 as asked. Arm B also cancels unrelated order 303. Each arm starts from a freshly recreated container."
T4_OUT=runs/t4_demo_$STAMP "$PY" scripts/demo_t4_collateral.py 2>&1 | quiet
T4_OUT=runs/t4_demo_$STAMP "$PY" scripts/demo_t4_analyze.py 2>&1 | quiet | sed -n '/^--- A_clean/,$p'
pause

h "4. LIVE: execute, find the inverse, TAKE it, read the state back (reversibility probe)"
echo "Cells: hold x pending (positive control, must come back REVERSIBLE), invoice x pending, cancel x pending."
mkdir -p "runs/grid_demo_$STAMP"
[ -f out/e1_order_pool.json ] && cp out/e1_order_pool.json "runs/grid_demo_$STAMP/"   # reuse the cached order pool (read-only copy)
GRID_DEMO=runs/grid_demo_$STAMP "$PY" scripts/demo_grid_cell.py --fresh --verbs invoice,cancel --states pending 2>&1 | quiet
echo
GRID_DEMO=runs/grid_demo_$STAMP "$PY" scripts/demo_summarise_grid.py
pause

h "5. Every reported number is re-derived from the recorded data (FR26)"
for s in 31_abstract_headline 37_evaluator_field_census 38_calibration_sensitivity 41_b7_verb_control 32_grid_figure; do
  printf "%-30s " "$s"; "$PY" "scripts/$s.py" 2>&1 | tail -1
done
echo
echo "Demo outputs: runs/t4_demo_$STAMP  runs/grid_demo_$STAMP"
