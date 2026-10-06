import os, json, time
SA="http://localhost:7780"; DEAD="http://localhost:1"
os.environ.update(WA_SHOPPING_ADMIN=f"{SA}/admin", WA_SHOPPING=DEAD, WA_REDDIT=DEAD,
                  WA_GITLAB=DEAD, WA_WIKIPEDIA=DEAD, WA_MAP=DEAD, WA_HOMEPAGE=DEAD)
import gymnasium, browsergym.webarena_verified  # noqa
env = gymnasium.make("browsergym/webarena_verified.257.470.2", headless=True, timeout=30000)
obs, info = env.reset()
print("RESET info keys:", sorted(info.keys()))
print(json.dumps({k:str(v)[:120] for k,v in info.items()}, indent=1)[:900])
obs, r, term, trunc, info = env.step("noop()")
print("\nSTEP info keys:", sorted(info.keys()))
print(json.dumps({k:str(v)[:200] for k,v in info.items()}, indent=1)[:1200])
env.close()
