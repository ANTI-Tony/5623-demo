import sys, re; sys.path.insert(0, '.')
from cawebagent.trace.runner import set_env
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
import gymnasium, browsergym.webarena_verified  # noqa
from browsergym.utils.obs import flatten_axtree_to_str
env = gymnasium.make("browsergym/webarena_verified.257.470.2", headless=True, timeout=30000)
obs, info = env.reset()
obs, *_ = env.step("goto('http://localhost:7780/admin/sales/order/view/order_id/302/')")
print("URL:", obs["url"]); print("err:", obs["last_action_error"][:150])
txt = flatten_axtree_to_str(obs["axtree_object"])
hits = [l for l in txt.split("\n") if re.search(r"cancel|hold|invoice|ship|credit memo|reorder|button", l, re.I)]
print(f"--- candidate controls ({len(hits)}) ---")
for l in hits[:30]: print("  ", l.strip()[:120])
print("--- order header ---")
for l in txt.split("\n"):
    if re.search(r"#302|Order & Account|Order Status|Pending|Processing|Complete", l): print("  ", l.strip()[:120])
env.close()
