"""Experiment 1 — consequence taxonomy over the benchmark's state-changing endpoints,
and: does consequence rise toward the end of the expected event sequence?
No environment required."""
import json, re, collections
from pathlib import Path
from webarena_verified.utils import get_package_assets_path

DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
OUT = Path(__file__).resolve().parents[1]/'out'

# ---- rule source: endpoint -> (action_class, tier, flags, MCP axes) -----------
# tier 0 = recoverable & no external change | 1 = state change, recoverable
# tier 2 = real / irreversible loss or externally visible
RULES = [
 # (regex, action_class, tier, flags, destructive, idempotent, openWorld)
 (r'/sales/order/cancel',            'order_cancel',      2, ['money','irreversible'], True,  True,  False),
 (r'/carts/mine/payment-information','order_place',       2, ['money','irreversible'], True,  False, True),
 (r'/review/product/delete',         'review_delete',     2, ['data_deletion'],        True,  False, False),
 (r'/order_shipment/save',           'shipment_create',   2, ['irreversible'],         True,  False, True),
 (r'/sales/order/addressSave',       'order_address_edit',2, ['money'],                True,  True,  False),
 (r'/contact/index/post',            'external_message',  2, ['external_comm'],        False, False, True),
 (r'/newsletter/subscriber/new',     'external_message',  2, ['external_comm'],        False, True,  True),
 (r'/api/v4/.*/(members|invitations)','member_invite',    2, ['permission_change'],    False, True,  True),
 (r'/api/v4/groups/.*/invitations',  'member_invite',     2, ['permission_change'],    False, True,  True),
 (r'/catalog/product/save',          'product_edit',      1, ['price_or_stock'],       True,  True,  False),
 (r'/catalog_rule|/sales_rule',      'pricing_rule_edit', 1, ['price_or_stock'],       True,  True,  False),
 (r'/product_attribute/save',        'product_edit',      1, [],                       True,  True,  False),
 (r'/cms/page/save',                 'cms_edit',          1, ['public_content'],       True,  True,  True),
 (r'/review/product/(post|save)',    'review_post',       1, ['public_content'],       False, False, True),
 (r'/customer/address/formPost',     'address_edit',      1, [],                       True,  True,  False),
 (r'/checkout/cart/add',             'cart_edit',         0, [],                       False, False, False),
 (r'/wishlist/index/add',            'wishlist_edit',     0, [],                       False, True,  False),
 (r'/repository/commits',            'repo_commit',       1, ['code_change'],          False, False, False),
 (r'/-/(update|create|blob)/',       'repo_file_edit',    1, ['code_change'],          True,  False, False),
 (r'/-/merge_requests',              'merge_request_open',1, ['code_change'],          False, False, False),
 (r'/-/issues|/api/v4/.*/issues',    'issue_create',      1, [],                       False, False, False),
 (r'/-/milestones',                  'milestone_create',  1, [],                       False, False, False),
 (r'/notes$|/notes\b',               'comment_post',      1, ['public_content'],       False, False, True),
 (r'/api/v4/projects/.*/fork',       'repo_fork',         1, [],                       False, True,  False),
 (r'/api/v4/projects$|/projects$',   'repo_create',       1, [],                       False, False, False),
 (r'/groups$',                       'group_create',      1, [],                       False, False, False),
 (r'toggle_star\.json',              'star_toggle',       0, [],                       False, True,  False),
 (r'/follow\.json',                  'follow_toggle',     0, [],                       False, True,  False),
 (r'/-/profile|/api/v4/user/status', 'profile_edit',      1, ['public_content'],       True,  True,  True),
 (r'/edit_biography',                'profile_edit',      1, ['public_content'],       True,  True,  True),
 (r'/create_forum',                  'forum_create',      1, ['public_content'],       False, False, True),
 (r'/submit',                        'post_create',       1, ['public_content'],       False, False, True),
 (r'/-/comment',                     'comment_post',      1, ['public_content'],       False, False, True),
 (r'/-/edit',                        'post_edit',         1, ['public_content'],       True,  True,  True),
 (r'/sv/\d+\.json',                  'vote',              0, [],                       False, True,  False),
 (r'(sub|unsub)scribe\.json',        'subscribe_toggle',  0, [],                       False, True,  False),
 (r'/api/graphql',                   'graphql_write',     1, [],                       True,  False, False),
 (r'/sales/order/addComment',        'order_comment',     1, [],                       False, False, False),
 (r'/dummy_bin',                     'external_message',  2, ['external_comm'],        False, False, True),
]
def classify(u):
    for rx, cls, tier, flags, d, i, o in RULES:
        if re.search(rx, u): return cls, tier, flags, dict(destructive=d, idempotent=i, openWorld=o)
    return 'UNCLASSIFIED', None, [], {}

def tt(t):
    for e in t['eval']:
        if e['evaluator']=='AgentResponseEvaluator': return e['expected'].get('task_type')

recs = []
for t in DS:
    seq = []
    for e in t['eval']:
        if e['evaluator']!='NetworkEventEvaluator': continue
        x = e['expected']; m = (x.get('http_method') or 'GET').upper()
        urls = x['url'] if isinstance(x['url'], list) else [x['url']]
        for u in urls:
            cls, tier, flags, mcp = classify(u)
            seq.append(dict(method=m, url=u, cls=cls, tier=(0 if m=='GET' and tier is None else tier),
                            flags=flags, mcp=mcp, is_mut=(m!='GET')))
    recs.append(dict(task_id=t['task_id'], tpl=t['intent_template_id'], tt=tt(t),
                     sites=t['sites'], seq=seq))

MUT = [ev for r in recs for ev in r['seq'] if ev['is_mut']]
print("="*72); print("EXP-1  Consequence taxonomy over state-changing endpoints"); print("="*72)
unc = [e for e in MUT if e['cls']=='UNCLASSIFIED']
print(f"state-changing events {len(MUT)}   unclassified {len(unc)} ({100*len(unc)/len(MUT):.1f}%)")
for u in collections.Counter(e['url'] for e in unc).most_common(10): print("   UNCLASSIFIED:", u)

print("\n[tier distribution over state-changing events]")
for k,v in sorted(collections.Counter(e['tier'] for e in MUT).items(), key=lambda x:(x[0] is None, x[0])):
    print(f"  tier {k}: {v:4d}  ({100*v/len(MUT):.1f}%)")
print("\n[action class]")
for k,v in collections.Counter(e['cls'] for e in MUT).most_common():
    tiers = {e['tier'] for e in MUT if e['cls']==k}
    print(f"  {k:22} {v:4d}  tier={sorted(tiers)}")

# ---- P5: does the LAST expected event carry the highest tier? ----------------
multi = [r for r in recs if len([e for e in r['seq'] if e['is_mut']]) >= 2]
rise = flat = fall = 0
for r in multi:
    ts = [e['tier'] for e in r['seq'] if e['is_mut'] and e['tier'] is not None]
    if len(ts) < 2: continue
    if ts[-1] > max(ts[:-1]): rise += 1
    elif ts[-1] == max(ts[:-1]): flat += 1
    else: fall += 1
print(f"\n[P5 probe] tasks with >=2 state-changing expectations: {len(multi)}")
print(f"  last event is strictly highest tier : {rise}")
print(f"  last event ties for highest tier    : {flat}")
print(f"  last event is NOT highest           : {fall}")

json.dump(recs, open(OUT/'exp1_taxonomy.json','w'))
print(f"\nwrote {OUT}/exp1_taxonomy.json")
