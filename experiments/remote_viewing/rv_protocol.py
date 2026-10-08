"""Blind-vault experiment: cryptographic commitments, not paranormal claims.

Only Python stdlib + cryptography. Never persist plaintext targets or passwords.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

PROTOCOL = "bean-rv-v1"
AD = b"bean-rv-v1:sealed-target"
# A finite but combinatorially large target space. All choices use OS CSPRNG.
FEATURES = {
    "painting": [
        ["a charcoal lighthouse", "a glass castle", "a copper whale", "a porcelain tree", "a golden staircase", "a floating clock"],
        ["under a violet moon", "inside a snow globe", "above a flooded city", "in a field of sunflowers", "in a foggy cathedral"],
        ["with six red balloons", "with a mirrored river", "and three green doors", "with a ring of fireflies", "beneath a fractured rainbow"],
    ],
    "vehicle": [
        ["a tracked rescue robot", "a steam-powered motorcycle", "an amphibious bus", "a three-wheeled race car", "a wooden airplane", "a futuristic snowplow"],
        ["painted cobalt blue", "covered in checkerboard tiles", "with iridescent panels", "painted burnt orange", "made of brushed aluminum"],
        ["carrying a grand piano", "with a giant brass propeller", "under an enormous umbrella", "towing a glass greenhouse", "with a spiral exhaust pipe"],
    ],
    "object": [
        ["an obsidian chessboard", "a transparent violin", "a giant hourglass", "a crystal compass", "a velvet telescope", "a hinged marble crown"],
        ["on a white sand dune", "in a rusted vault", "under an orange spotlight", "inside a frozen lake", "on a rotating pedestal"],
        ["surrounded by feathers", "entwined with ivy", "beside a silver ladder", "next to three identical keys", "casting a star-shaped shadow"],
    ],
    "concept": [
        ["a fable about regret", "an allegory about fairness", "a parable about patience", "a story about misplaced loyalty", "a thought experiment about identity"],
        ["narrated by a skeptical gardener", "told through letters from a sailor", "written as a courtroom argument", "recalled by an elderly pianist", "told by an unreliable historian"],
        ["ending in reconciliation", "ending with an unanswered question", "ending with a lost object recovered", "ending in joyful disbelief", "ending with a quiet refusal"],
    ],
    "geometry": [
        ["a hollow red dodecahedron", "a blue spiral inside a cube", "a yellow five-point star", "a purple torus", "a green stepped pyramid"],
        ["floating over a checkerboard", "nested in a translucent sphere", "resting on a black triangle", "reflected in four mirrors", "suspended by golden threads"],
        ["with two missing corners", "cut by a diagonal beam", "covered in tiny dots", "surrounded by concentric rings", "casting two overlapping shadows"],
    ],
}
def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())

def json_read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def new_candidates() -> tuple[str, list[str]]:
    category = secrets.choice(tuple(FEATURES))
    dimensions = FEATURES[category]
    descriptions = set()
    while len(descriptions) < 4:
        descriptions.add(", ".join(secrets.choice(dim) for dim in dimensions))
    # Sorting makes candidate ordering independent of hash-set iteration.
    ordered = sorted(descriptions)
    secrets.SystemRandom().shuffle(ordered)
    return category, ordered

def derive(passphrase: str, salt: bytes) -> bytes:
    if not passphrase or len(passphrase) < 16:
        raise ValueError("Vault passphrase must contain at least 16 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))

def initialize(root: Path, passphrase: str) -> dict:
    if root.exists():
        raise FileExistsError("Challenge directory already exists; never overwrite a trial")
    category, candidates = new_candidates()
    challenge_id = secrets.token_hex(16)
    bundle = {
        "protocol": PROTOCOL,
        "challenge_id": challenge_id,
        "category": category,
        "candidates": candidates,
        "target_index": secrets.randbelow(4),
        "commit_nonce": secrets.token_hex(32),
    }
    commitment = digest(canonical(bundle))
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    encrypted = AESGCM(derive(passphrase, salt)).encrypt(iv, canonical(bundle), AD)
    manifest = {
        "protocol": PROTOCOL,
        "challenge_id": challenge_id,
        "commitment_sha256": commitment,
        "candidate_count": 4,
        "created_utc": timestamp(),
        "target_generation": "os-csprng/finite-combinatorial-pool",
        "status": "CREATED",
    }
    root.mkdir(parents=True, mode=0o700)
    try:
        exclusive(root / "vault.json", canonical({"salt": salt.hex(), "iv": iv.hex(), "ciphertext": encrypted.hex()}))
        exclusive(root / "challenge.json", canonical(manifest))
    except BaseException:
        raise
    return manifest

def observation(root: Path, description: str, chat_reference: str) -> dict:
    if not (1 <= len(description) <= 200000):
        raise ValueError("Observation must contain between 1 and 200000 characters")
    if not (1 <= len(chat_reference) <= 500):
        raise ValueError("Chat reference is required (may be an external transcript ID)")
    manifest = json_read(root / "challenge.json")
    if (root / "closed.json").exists():
        raise ValueError("Trial already closed")
    payload = {
        "protocol": PROTOCOL,
        "challenge_id": manifest["challenge_id"],
        "description": description,
        "chat_reference": chat_reference,
        "sealed_utc": timestamp(),
    }
    sealed = {"observation": payload, "observation_sha256": digest(canonical(payload))}
    exclusive(root / "observation.lock.json", canonical(sealed))
    return {"challenge_id": manifest["challenge_id"], "observation_sha256": sealed["observation_sha256"], "sealed_utc": payload["sealed_utc"]}

def close_trial(root: Path, transcript_hash: str, chat_closed: bool) -> dict:
    if chat_closed is not True:
        raise ValueError("Operator must explicitly attest that the viewing chat is closed")
    record = json_read(root / "observation.lock.json")
    if digest(canonical(record["observation"])) != record["observation_sha256"]:
        raise ValueError("Stored observation tampered with")
    if not hmac.compare_digest(record["observation_sha256"], transcript_hash):
        raise ValueError("Observation digest mismatch")
    payload = {
        "protocol": PROTOCOL,
        "challenge_id": record["observation"]["challenge_id"],
        "observation_sha256": transcript_hash,
        "operator_attests_chat_closed": True,
        "closed_utc": timestamp(),
    }
    exclusive(root / "closed.json", canonical(payload))
    return payload

def reveal(root: Path, passphrase: str) -> dict:
    if not (root / "closed.json").is_file():
        raise PermissionError("Reveal forbidden until observation is sealed and chat closure attested")
    locked = json_read(root / "observation.lock.json")
    closed = json_read(root / "closed.json")
    if digest(canonical(locked["observation"])) != locked["observation_sha256"]:
        raise ValueError("Stored observation tampered with")
    if not hmac.compare_digest(closed["observation_sha256"], locked["observation_sha256"]):
        raise ValueError("Closure does not match sealed observation")
    vault = json_read(root / "vault.json")
    plaintext = AESGCM(derive(passphrase, bytes.fromhex(vault["salt"]))).decrypt(
        bytes.fromhex(vault["iv"]), bytes.fromhex(vault["ciphertext"]), AD
    )
    manifest = json_read(root / "challenge.json")
    if not hmac.compare_digest(digest(plaintext), manifest["commitment_sha256"]):
        raise ValueError("Commitment verification failed")
    bundle = json.loads(plaintext)
    if bundle["challenge_id"] != manifest["challenge_id"] or bundle["protocol"] != PROTOCOL:
        raise ValueError("Challenge mismatch")
    return {
        "verified": True,
        "bundle": bundle,
        "target": bundle["candidates"][bundle["target_index"]],
        "commitment_sha256": manifest["commitment_sha256"],
        "sealed_observation": locked,
        "closure": closed,
    }
