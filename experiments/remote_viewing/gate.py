"""Separate blind judging from the final target reveal."""
import math
from pathlib import Path
try:
    from .rv_protocol import reveal, exclusive, json_read, canonical, digest, timestamp
except ImportError:
    from rv_protocol import reveal, exclusive, json_read, canonical, digest, timestamp

def blind_packet(root: Path, passphrase: str) -> dict:
    """Only accessible after transcript seal + verified closure; hides target index."""
    record = reveal(root, passphrase)
    bundle = record["bundle"]
    return {
        "protocol": bundle["protocol"],
        "challenge_id": bundle["challenge_id"],
        "candidates": bundle["candidates"],
        "observation": record["sealed_observation"]["observation"],
        "warning": "ALL FOUR CANDIDATES ARE PRESENTED IN BLIND ORDER; SELECT ONLY ONE",
    }

def judge(root: Path, index: int, judge_id: str) -> dict:
    if not (root / "closed.json").exists():
        raise PermissionError("Cannot judge before operator confirms chat closure")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= 3:
        raise ValueError("Selection must be an integer 0, 1, 2, or 3")
    if not isinstance(judge_id, str) or not (1 <= len(judge_id) <= 100):
        raise ValueError("Judge ID required")
    manifest = json_read(root / "challenge.json")
    selection = {
        "challenge_id": manifest["challenge_id"],
        "selected_candidate_index": index,
        "judge_id": judge_id,
        "locked_utc": timestamp(),
    }
    locked = {"judgement": selection, "judgement_sha256": digest(canonical(selection))}
    exclusive(root / "judgement.lock.json", canonical(locked))
    return {"judgement_sha256": locked["judgement_sha256"],
            "challenge_id": manifest["challenge_id"], "locked": True}

def final_result(root: Path, passphrase: str) -> dict:
    if not (root / "judgement.lock.json").exists():
        raise PermissionError("Cannot reveal target before blind judgement sealed")
    record = reveal(root, passphrase)
    judgement = json_read(root / "judgement.lock.json")
    if digest(canonical(judgement["judgement"])) != judgement["judgement_sha256"]:
        raise ValueError("Judgement digest invalid")
    if judgement["judgement"]["challenge_id"] != record["bundle"]["challenge_id"]:
        raise ValueError("Judgement belongs to another challenge")
    correct = record["bundle"]["target_index"]
    chosen = judgement["judgement"]["selected_candidate_index"]
    record.update({
        "judgement": judgement,
        "hit": chosen == correct,
        "chance_probability_per_trial": 0.25,
    })
    return record

def binomial_tail(hits: int, trials: int, chance: float = 0.25) -> float:
    """One-sided P(X >= hits) under prespecified independent equal-probability null."""
    if not 0 <= hits <= trials or trials < 1 or not 0 < chance < 1:
        raise ValueError("Invalid binomial test")
    if hits == 0:
        return 1.0
    logs = [
        math.lgamma(trials + 1) - math.lgamma(i + 1) - math.lgamma(trials - i + 1)
        + i * math.log(chance) + (trials - i) * math.log1p(-chance)
        for i in range(hits, trials + 1)
    ]
    peak = max(logs)
    return min(1.0, math.exp(peak) * math.fsum(math.exp(x - peak) for x in logs))
