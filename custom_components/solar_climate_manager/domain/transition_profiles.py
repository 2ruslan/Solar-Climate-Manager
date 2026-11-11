"""Cycle-balanced summaries; neighbouring minutes are not independent trials."""

from statistics import median
from typing import Any


def weighted_median(values: list[tuple[float, float]]) -> float:
    ordered = sorted(values)
    half = sum(weight for _, weight in ordered)/2
    accumulated = 0.0
    for i, (value, weight) in enumerate(ordered):
        accumulated += weight
        if accumulated >= half:
            if accumulated == half and i+1 < len(ordered):
                return (value+ordered[i+1][0])/2
            return value
    return ordered[-1][0]


def summarize(rows: list[dict[str, Any]], now: float) -> dict[str, Any]:
    cycles: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        cycles.setdefault(row.get("cycle", row["time"]), []).append(row)
    values: list[tuple[float, float]] = []
    qualities: list[float] = []
    counts: list[int] = []
    reason_shares: dict[str, float] = {}
    margins = []
    for samples in cycles.values():
        weights = [max(.01, min(1., r.get("quality", 1.))) for r in samples]
        quality = sum(weights)/len(weights)
        age = max(0, now-max(r["time"] for r in samples))
        values.append((weighted_median([(r["estimate"], w) for r, w in zip(samples, weights)]),
                       quality*2**(-age/(14*86400))))
        qualities.append(quality)
        counts.append(len(samples))
        margins.append(median((r["high"]-r["low"])/2 for r in samples))
        for reason in {reason for r in samples for reason in r.get("reasons", [])}:
            reason_shares[reason] = reason_shares.get(reason, 0)+sum(
                reason in r.get("reasons", []) for r in samples)/len(samples)
    center = weighted_median(values)
    spread = weighted_median([(abs(v-center), weight) for v, weight in values])
    tolerance = max(150, center*.25)
    supported = sum(q >= .5 and count >= 3 and abs(v-center) <= tolerance
                    for (v, _), q, count in zip(values, qualities, counts))
    reasons = sorted(reason for reason, share in reason_shares.items() if share/len(cycles) >= .25)
    updated = max(r["time"] for r in rows)
    if len(rows) < 20:
        reasons.append("few_samples")
    if supported < 3:
        reasons.append("few_cycles")
    if spread > tolerance:
        reasons.append("variable_power")
    if now-updated > 7*86400:
        reasons.append("old_samples")
    quality = sum(qualities)/len(qualities)
    moderate = supported >= 3 and len(rows) >= 20 and quality >= .6 and spread <= tolerance and now-updated <= 7*86400
    margin = median(margins)+spread+150/max(1, supported)**.5
    return {"estimate": round(center, 1), "low": round(max(0, center-margin), 1),
            "high": round(min(10000, center+margin), 1), "windows": len(rows),
            "minutes": sum(r["seconds"] for r in rows)/60, "cycles": len(cycles),
            "supported_cycles": supported, "quality_percent": round(quality*100),
            "source": "ruptures", "confidence": "moderate" if moderate else "low",
            "reasons": reasons, "updated_at": updated}
