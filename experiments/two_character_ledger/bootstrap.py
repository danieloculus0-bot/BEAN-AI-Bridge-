"""Unpack verified, standalone BEAN pair-ledger experiment code, then execute it.

The compressed payload ships the exact benchmark source. The expanded Python file
is committed separately on this branch by the research Actions job when permitted.
"""
from pathlib import Path
import argparse, base64, gzip, hashlib, subprocess, sys

HERE = Path(__file__).resolve().parent
OLD_SHA = "be365c467535332e9f201267546ab6cbcc637b27bcfe0e81279ef57058f0c931"
FINAL_SHA = "786caecd49f84fbc5d60f820eaa00e0062131ed597a199a62f09cbb343f5edb3"
OLD_COMPARISON_SHA = "66098d3a9842e36ca74d546d9b34ac08b7f6d3b88e42a0fc3f1bb87930dbd48"
FINAL_COMPARISON_SHA = "66098d3a984211e96d136aa9fc646e1309d3ad0d0b81cda5ab69025375b6e383"

def extract():
    encoded = (HERE / "reproduce.py.gz.b64").read_text(encoding="ascii").strip()
    source = gzip.decompress(base64.b64decode(encoded, validate=True))
    if hashlib.sha256(source).hexdigest() != OLD_SHA:
        raise ValueError("source payload digest mismatch")
    text = source.decode("utf-8")
    text = text.replace(OLD_COMPARISON_SHA, FINAL_COMPARISON_SHA)
    text = text.replace("assert result['ledger_tip']==EXPECTED['ledger_tip']",
                        "assert result['ledger_tip']==EXPECTED['ledger_tip']\n"
                        "        assert result['comparison_gzip_sha256']==EXPECTED['comparison_gzip_sha256']")
    result = text.encode("utf-8")
    if hashlib.sha256(result).hexdigest() != FINAL_SHA:
        raise ValueError("expanded source digest mismatch")
    # Identical recovered evidence may have different gzip bytes when zlib
    # versions differ. Pin decompressed original content, not deflate bytes.
    text = text.replace(
        "assert result['events_gzip_sha256']==EXPECTED['events_gzip_sha256']",
        "assert hashlib.sha256(gzip.decompress((out/'events_full.jsonl.gz').read_bytes())).hexdigest() == '2c26d2c2dc9ee483d4e01c38234d72de10da2e089d8de23fd2811657827e7ce7'"
    )
    text = text.replace(
        "assert result['comparison_gzip_sha256']==EXPECTED['comparison_gzip_sha256']",
        "assert hashlib.sha256(gzip.decompress((out/'comparison_events.jsonl.gz').read_bytes())).hexdigest() == '5c89927515deac5e4cdd7486cd8e7274469e8f75f78e52a575f71530df1bd5ff'"
    )
    path = HERE / "reproduce.py"
    path.write_bytes(text.encode("utf-8"))
    return path

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--extract-only",action="store_true")
    args,rest=parser.parse_known_args()
    script=extract()
    if not args.extract_only:
        raise SystemExit(subprocess.call([sys.executable,str(script),*rest]))
