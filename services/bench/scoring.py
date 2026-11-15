"""Versioned objective scoring; missing evidence remains visible."""

from collections import defaultdict
from statistics import mean, median, pstdev

SCORING_VERSION = 1
WEIGHTS = {"correctness": 45, "regression": 20, "quality": 10, "reliability": 10, "efficiency": 10, "safety": 5}


def score_trial(checks: list[dict], metrics: dict) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for check in checks:
        if check["category"] not in WEIGHTS or check["status"] not in {"passed", "failed", "error"}:
            raise ValueError("Invalid grader result")
        grouped[check["category"]].append(check)
    breakdown = {
        category: (100 * sum(item["status"] == "passed" for item in grouped[category]) / len(grouped[category])
                   if grouped[category] else None)
        for category in WEIGHTS
    }
    duration = metrics.get("duration_ms")
    budget = metrics.get("budget_ms")
    if duration is not None and budget is not None and budget > 0:
        breakdown["efficiency"] = max(0, min(100, 100 * (budget - duration) / budget))
    score = round(sum(WEIGHTS[key] * (value or 0) / 100 for key, value in breakdown.items()), 2)
    passed = bool(grouped["correctness"]) and all(
        item["status"] == "passed" for item in checks if item.get("required", False)
    ) and all(item["status"] == "passed" for item in grouped["correctness"])
    if not passed:
        score = min(score, 49.0)
    return {"score": score, "passed": passed, "breakdown": breakdown, "metrics": metrics,
            "scoring_version": SCORING_VERSION, "checks": checks}


def compare_results(left: dict, right: dict) -> dict:
    if left["dataset_digest"] != right["dataset_digest"]:
        raise ValueError("Cannot compare different benchmark datasets")
    if left.get("task_ids") != right.get("task_ids"):
        raise ValueError("Cannot compare different benchmark tasks")
    def delta(key: str) -> float | None:
        return round(right[key] - left[key], 2) if left.get(key) is not None and right.get(key) is not None else None
    return {"dataset_digest": left["dataset_digest"], "score_delta": delta("score"),
            "pass_rate_delta": delta("success_rate"), "duration_ms_delta": delta("average_duration_ms"),
            "token_count_delta": delta("average_token_count"),
            "dimension_deltas": {
                key: (round(right["dimension_scores"][key] - left["dimension_scores"][key], 2)
                      if left["dimension_scores"][key] is not None and right["dimension_scores"][key] is not None else None)
                for key in WEIGHTS
            }}


def summarize_trials(trials: list[dict]) -> dict:
    scored = [trial["result"] for trial in trials if trial["result"] is not None]
    agent_failures = sum(trial["status"] == "FAILED" and trial["result"] is None for trial in trials)
    values = [result["score"] for result in scored] + [0] * agent_failures
    count = len(values)
    durations = [result["metrics"]["duration_ms"] for result in scored if result["metrics"].get("duration_ms") is not None]
    tokens = [result["metrics"]["token_count"] for result in scored if result["metrics"].get("token_count") is not None]
    dimensions = {}
    for key in WEIGHTS:
        present = [result["breakdown"][key] for result in scored if result["breakdown"].get(key) is not None]
        dimensions[key] = round(mean(present + [0] * agent_failures), 2) if present else None
    failures: dict[str, int] = {}
    for trial in trials:
        if trial["status"] in {"FAILED", "ERROR", "CANCELLED"}:
            category = trial.get("failure_category") or trial["status"].lower()
            failures[category] = failures.get(category, 0) + 1
    return {"score": round(mean(values), 2) if values else None,
            "score_denominator": count, "scored_count": len(scored),
            "pass_count": sum(trial["status"] == "PASSED" for trial in trials),
            "trial_count": len(trials),
            "success_rate": sum(trial["status"] == "PASSED" for trial in trials) / count if count else None,
            "median_score": round(median(values), 2) if values else None,
            "score_variation": round(pstdev(values), 2) if values else None,
            "average_duration_ms": round(mean(durations), 2) if durations else None,
            "average_token_count": round(mean(tokens), 2) if tokens else None,
            "infrastructure_error_count": sum(trial["status"] == "ERROR" for trial in trials),
            "cancelled_count": sum(trial["status"] == "CANCELLED" for trial in trials),
            "agent_failure_count": agent_failures, "failure_distribution": failures,
            "dimension_scores": dimensions}
