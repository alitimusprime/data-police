from collections import deque


def distances(start, edges, reverse=False):
    adjacency = {}
    for source, target in edges:
        if reverse:
            source, target = target, source
        adjacency.setdefault(source, []).append(target)
    found = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for child in adjacency.get(node, []):
            if child not in found:
                found[child] = found[node] + 1
                queue.append(child)
    found.pop(start, None)
    return found


def related(a, b, edges):
    return a == b or b in distances(a, edges) or a in distances(b, edges)


def rank_candidates(anomalies, edges, evidence_by_anomaly):
    """Version 1: evidence ranking, deliberately not a calibrated probability."""
    observed_assets = {a.dataset_id for a in anomalies}
    output = []
    for asset in sorted(observed_assets):
        own = [a for a in anomalies if a.dataset_id == asset]
        downstream = distances(asset, edges)
        upstream = distances(asset, edges, reverse=True)
        explained = len((set(downstream) | {asset}) & observed_assets) / max(1, len(observed_assets))
        precedence = 1 if not (set(upstream) & observed_assets) else 0.25
        direct_kinds = {a.kind for a in own}
        direct = 1 if direct_kinds & {"schema_drift", "quality_failure", "pipeline_failure"} else 0.65
        corroboration = min(1, len(direct_kinds) / 3)
        strength = 1 if any(a.severity == "critical" for a in own) else 0.6
        signals = {
            "Upstream position": round(25 * precedence, 1),
            "Affected paths explained": round(30 * explained, 1),
            "Direct failure evidence": round(20 * direct, 1),
            "Independent monitor types": round(15 * corroboration, 1),
            "Observed severity": round(10 * strength, 1),
        }
        output.append(
            {
                "dataset_id": asset,
                "score": round(sum(signals.values()), 1),
                "contributions": signals,
                "evidence_ids": [evidence_by_anomaly[a.id] for a in own if a.id in evidence_by_anomaly],
            }
        )
    return sorted(output, key=lambda c: (-c["score"], c["dataset_id"]))
