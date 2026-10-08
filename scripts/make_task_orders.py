"""Task orders for the order-robustness experiment (DECISIONS 2026-10-08, final design).

Domains adjacent ("blocks"): the 20 manifest domain blocks are shuffled, then the tasks inside each block,
with one random.Random(seed); tasks of a domain stay consecutive.
Domains mixed: "random" = all 101 tasks shuffled uniformly with random.Random(seed); "interleave" = round robin
over the manifest blocks (block 1 task 1, block 2 task 1, ..., block 1 task 2, ...), skipping exhausted blocks,
so consecutive tasks come from different domains.

Writes data/experiment_splits/task_orders/<name>.json = {name, kind, seed, definition, task_ids, domains}.
"""
import json
import random
from pathlib import Path

MANIFEST = Path("data/experiment_splits/continual_domain_blocks/manifest.json")
OUT = Path("data/experiment_splits/task_orders")


def blocks() -> list[tuple[str, list[str]]]:
    m = json.loads(MANIFEST.read_text())
    return [(b["application_type"], list(b["task_ids"])) for b in m["batches"]]


def shuffled_blocks(seed: int) -> list[str]:
    rng = random.Random(seed)
    bs = [(d, list(ts)) for d, ts in blocks()]
    rng.shuffle(bs)
    for _, ts in bs:
        rng.shuffle(ts)
    return [t for _, ts in bs for t in ts]


def uniform(seed: int) -> list[str]:
    ids = [t for _, ts in blocks() for t in ts]
    random.Random(seed).shuffle(ids)
    return ids


def interleave() -> list[str]:
    queues = [list(ts) for _, ts in blocks()]
    out = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


ORDERS = [
    ("blocks_seed11", "domains_adjacent", 11, shuffled_blocks(11),
     "domain blocks shuffled, then tasks within each block, random.Random(11)"),
    ("random_seed29", "domains_mixed", 29, uniform(29), "all tasks shuffled uniformly, random.Random(29)"),
    ("blocks_seed47", "domains_adjacent", 47, shuffled_blocks(47),
     "domain blocks shuffled, then tasks within each block, random.Random(47)"),
    ("interleave", "domains_mixed", None, interleave(),
     "round robin over manifest domain blocks, skipping exhausted blocks"),
]

if __name__ == "__main__":
    domain_of = {t: d for d, ts in blocks() for t in ts}
    all_ids = sorted(domain_of)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, kind, seed, ids, definition in ORDERS:
        assert sorted(ids) == all_ids and len(ids) == 101, name
        same_adjacent = sum(domain_of[a] == domain_of[b] for a, b in zip(ids, ids[1:]))
        (OUT / f"{name}.json").write_text(json.dumps(
            {"name": name, "kind": kind, "seed": seed, "definition": definition, "task_ids": ids,
             "domains": [domain_of[t] for t in ids]}, indent=1) + "\n")
        print(f"{name:15s} {kind:17s} adjacent same-domain pairs {same_adjacent:3d}/100  first {ids[:4]}")
