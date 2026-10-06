"""Print the cells a demo grid run measured, one line each, from its JSON.

Reads only the demo directory ($GRID_DEMO); never the recorded out/e1_grid.json.
"""
import json, os, sys
from pathlib import Path

d = Path(os.environ.get('GRID_DEMO', sys.argv[1] if len(sys.argv) > 1 else 'runs/grid_demo'))
cells = json.loads((d / 'e1_grid.json').read_text())
print(f"{'cell':<26} {'before':<11} {'after action':<13} {'inverse taken':<28} {'after inverse':<14} verdict")
print('-' * 104)
for c in cells:
    cell = f"{c['verb']} x {c['state']}" + ('  [control]' if c.get('control') or (c['verb'], c['state']) == ('hold', 'pending') else '')
    inv = c.get('inverse_taken') or '-'
    if c.get('inverse_commit_control'):
        inv += f" + {c['inverse_commit_control']}"
    if c.get('outcome') != 'MEASURED':
        verdict = c.get('outcome')
    elif c.get('reversible'):
        verdict = 'REVERSIBLE'
    elif c.get('inverse_taken'):
        verdict = 'NOT REVERSIBLE (inverse taken, state not restored)'
    else:
        verdict = 'NOT REVERSIBLE (no inverse offered)'
    print(f"{cell:<26} {str(c.get('pre_status')):<11} {str(c.get('post_status')):<13} {inv:<28} {str(c.get('undo_status') or '-'):<14} {verdict}")
    if c.get('lost'):
        print(f"{'':<26} controls lost by the action: {', '.join(c['lost'])}")
