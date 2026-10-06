"""Find the real UI elements needed to cancel an order (for the scripted agent)."""
import sys; sys.path.insert(0, '.')
from cawebagent.trace.runner import set_env, run_episode
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
import gymnasium, browsergym.webarena_verified  # noqa
from browsergym.core.action.highlevel import HighLevelActionSet

env = gymnasium.make("browsergym/webarena_verified.257.470.2", headless=True, timeout=30000)
obs, info = env.reset()
# navigate straight to the order view page for order 302
obs, r, t, tr, info = env.step("goto('http://localhost:7780/admin/sales/order/')")
ax = obs["axtree_object"]
from browsergym.utils.obs import flatten_axtree_to_str
txt = flatten_axtree_to_str(ax)
print("URL:", obs["url"], "err:", obs["last_action_error"][:100])
import re
# show searchable/actionable elements
lines = [l for l in txt.split("\n") if re.search(r"button|link|textbox|searchbox|row", l, re.I)]
print(f"axtree lines={len(txt.split(chr(10)))}, actionable={len(lines)}")
for l in lines[:45]: print("  ", l.strip()[:130])
env.close()
