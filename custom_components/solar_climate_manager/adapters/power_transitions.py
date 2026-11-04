"""Bounded local change detection, called only inside the SQLite executor job."""

from statistics import median
from typing import Any

Record = tuple[float, float, dict[str, Any]]
MAX_EDGES = 96
SIDE = 10


def active(record: Record) -> tuple[str, ...]:
    return tuple(sorted(k for k, v in record[2].items() if v is not None))


def detect(records: list[Record]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Use known off/single-AC edges to anchor a local background estimate.

    A detected step is evidence, not proof of appliance identity. Only propagate
    within an uninterrupted single-AC run, at most one hour from an anchor.
    """
    import numpy as np

    from ..ruptures_vendor import Binseg

    states = [active(r) for r in records]
    edges = [i for i in range(1, len(records)) if states[i] != states[i-1]
             and ((not states[i-1] and len(states[i]) == 1)
                  or (not states[i] and len(states[i-1]) == 1))][-MAX_EDGES:]
    anchors: dict[tuple[int, int, str], list[tuple[float, float, float]]] = {}
    accepted = 0
    for edge in edges:
        start, end = max(0, edge-SIDE), min(len(records), edge+SIDE)
        window = records[start:end]
        split = edge-start
        if split < 3 or len(window)-split < 3:
            continue
        if any(not 0 < b[0]-a[0] <= 120 for a, b in zip(window, window[1:])):
            continue
        if any(s != states[edge-1] for s in states[start:edge]) or any(
                s != states[edge] for s in states[edge:end]):
            continue
        values = np.array([r[1] for r in window], dtype=float)
        detector = Binseg(model="l1", min_size=3, jump=1).fit(values)
        try:
            cuts = detector.predict(n_bkps=1)
        finally:
            detector.single_bkp.cache_clear()
        cut = cuts[0]
        if abs(window[cut][0]-records[edge][0]) > 180:
            continue
        before, after = float(median(values[:cut])), float(median(values[cut:]))
        starting = bool(states[edge])
        step = after-before if starting else before-after
        noise = float(median(abs(v-before) for v in values[:cut])
                      + median(abs(v-after) for v in values[cut:]))
        if step <= max(75, noise*2):
            continue
        device = (states[edge] if starting else states[edge-1])[0]
        # Background uses actual off-state samples, not a delayed compressor step.
        off = window[:split] if starting else window[split:]
        baseline = float(median(r[1] for r in off))
        run_start = edge if starting else edge-1
        run_end = run_start+1
        while run_start > 0 and states[run_start-1] == (device,) and records[run_start][0]-records[run_start-1][0] <= 120:
            run_start -= 1
        while run_end < len(records) and states[run_end] == (device,) and records[run_end][0]-records[run_end-1][0] <= 120:
            run_end += 1
        anchors.setdefault((run_start, run_end, device), []).append((records[edge][0], baseline, noise))
        accepted += 1
    evidence: dict[str, list[dict[str, Any]]] = {}
    for (start, end, device), points in anchors.items():
        for i in range(start, end):
            stamp, _, members = records[i]
            nearest = min(points, key=lambda p: abs(stamp-p[0]))
            distance = abs(stamp-nearest[0])
            if distance > 3600:
                continue
            baseline = nearest[1]
            reasons = ["transition_estimate"]
            if len(points) == 1:
                reasons.append("single_transition")
            else:
                first, last = min(points), max(points)
                fraction = max(0, min(1, (stamp-first[0])/max(1, last[0]-first[0])))
                baseline = first[1]+fraction*(last[1]-first[1])
                if abs(first[1]-last[1]) > 200:
                    reasons.append("noisy_background")
            if stamp-records[start][0] < 600:
                reasons.append("startup")
            if members[device].get("outdoor") is None:
                reasons.append("missing_outdoor")
            total = median(r[1] for r in records[max(start, i-2):min(end, i+3)])
            estimate = min(10000, max(0, total-baseline))
            margin = 100+nearest[2]*2+distance/12
            evidence.setdefault(device, []).append({
                "time": stamp, "conditions": members[device], "estimate": round(estimate, 1),
                "low": round(max(0, estimate-margin), 1), "high": round(min(10000, estimate+margin), 1),
                "seconds": min(60, stamp-records[i-1][0]) if i > start else 0,
                "identified": True, "reasons": reasons, "source": "ruptures",
            })
    return {k: sorted(rows, key=lambda r: r["time"])[-2000:] for k, rows in evidence.items()}, accepted
