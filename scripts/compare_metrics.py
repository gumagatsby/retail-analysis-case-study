"""Fail if a fresh run of the analysis gives different figures from the committed out/metrics.json.

Bootstrap intervals use a fixed seed, so every figure should match exactly; floats are compared
to 9 significant figures to allow for platform rounding.
"""
import json
import math
import sys
from pathlib import Path


def walk(a, b, path="") -> list[str]:
    if isinstance(a, dict):
        keys = set(a) | set(b)
        return [d for k in sorted(keys) for d in walk(a.get(k), b.get(k), f"{path}.{k}")]
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in walk(x, y, f"{path}[{i}]")]
    if isinstance(a, float) and isinstance(b, (int, float)):
        return [] if math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) else [f"{path}: {a} != {b}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


diffs = walk(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
print("\n".join(diffs[:20]) or "all figures match")
sys.exit(1 if diffs else 0)
