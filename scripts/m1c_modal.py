import sys, re; sys.path.insert(0,'.')
from cawebagent.trace.runner import set_env
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
import gymnasium, browsergym.webarena_verified  # noqa
from browsergym.utils.obs import flatten_axtree_to_str
env=gymnasium.make("browsergym/webarena_verified.257.470.2", headless=True, timeout=30000)
obs,_=env.reset()
obs,*_=env.step("goto('http://localhost:7780/admin/sales/order/view/order_id/302/')")
obs,*_=env.step("click('736')")
print("after click, err:", obs["last_action_error"][:120])
txt=flatten_axtree_to_str(obs["axtree_object"])
hits=[l for l in txt.split("\n") if re.search(r"\bOK\b|Cancel|dialog|modal|sure|confirm", l, re.I)]
print(f"--- modal-ish elements ({len(hits)}) ---")
for l in hits[:25]: print("  ", l.strip()[:120])
env.close()
