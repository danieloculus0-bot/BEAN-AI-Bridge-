"""Local prototype reveal portal. Put behind TLS + independent audit custody before research use."""
import argparse
import getpass
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from .rv_protocol import initialize, observation, close_trial, json_read
    from .gate import blind_packet, judge, final_result
except ImportError:
    from rv_protocol import initialize, observation, close_trial, json_read
    from gate import blind_packet, judge, final_result

MAX_BODY = 256 * 1024

def authenticated(handler, env_key: str) -> bool:
    expected = os.environ.get(env_key, "")
    candidate = handler.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(candidate.encode(), ("Bearer " + expected).encode())

def server(root: Path, host: str, port: int):
    if not (root / "challenge.json").is_file():
        raise FileNotFoundError("Create challenge before running portal")
    required = ["RV_VIEWER_TOKEN", "RV_ADMIN_TOKEN", "RV_JUDGE_TOKEN", "RV_REVIEWER_TOKEN", "RV_VAULT_PASSPHRASE"]
    missing = [x for x in required if not os.environ.get(x)]
    if missing:
        raise RuntimeError("Missing environment secrets: " + ", ".join(missing))
    if len({os.environ[x] for x in required[:4]}) != 3:
        raise RuntimeError("Role tokens must be distinct")
    if host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("RV_ALLOW_REMOTE_HTTP") != "I_UNDERSTAND":
        raise RuntimeError("Refusing non-local plain HTTP. Use a TLS reverse proxy.")
    class Handler(BaseHTTPRequestHandler):
        def json_reply(self, status, data):
            raw = json.dumps(data, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/v1/challenge":
                m = json_read(root / "challenge.json")
                self.json_reply(200, {"protocol": m["protocol"], "challenge_id": m["challenge_id"],
                                      "commitment_sha256": m["commitment_sha256"],
                                      "candidate_count": m["candidate_count"]})
            elif self.path == "/v1/status":
                self.json_reply(200, {
                    "observation_sealed": (root / "observation.lock.json").is_file(),
                    "chat_closed_attested": (root / "closed.json").is_file(),
                    "blind_judgement_sealed": (root / "judgement.lock.json").is_file(),
                })
            else:
                self.json_reply(404, {"error": "not found"})

        def do_POST(self):
            access = {
                "/v1/observation": "RV_VIEWER_TOKEN",
                "/v1/close": "RV_ADMIN_TOKEN",
                "/v1/judge-packet": "RV_JUDGE_TOKEN",
                "/v1/judge": "RV_JUDGE_TOKEN",
                "/v1/reveal": "RV_REVIEWER_TOKEN",
            }
            if self.path not in access:
                return self.json_reply(404, {"error": "not found"})
            if not authenticated(self, access[self.path]):
                return self.json_reply(401, {"error": "unauthorized"})
            try:
                size = int(self.headers.get("Content-Length", "-1"))
                if size < 2 or size > MAX_BODY:
                    return self.json_reply(413, {"error": "invalid request size"})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/v1/observation":
                    result = observation(root, body["description"], body["chat_reference"])
                elif self.path == "/v1/close":
                    result = close_trial(root, body["observation_sha256"], body.get("chat_closed"))
                elif self.path == "/v1/judge-packet":
                    result = blind_packet(root, os.environ["RV_VAULT_PASSPHRASE"])
                elif self.path == "/v1/judge":
                    result = judge(root, body["selected_candidate_index"], body["judge_id"])
                else:
                    result = final_result(root, os.environ["RV_VAULT_PASSPHRASE"])
                return self.json_reply(200, result)
            except (KeyError, ValueError, TypeError) as exc:
                return self.json_reply(400, {"error": str(exc)})
            except FileExistsError:
                return self.json_reply(409, {"error": "record already sealed, immutable"})
            except (FileNotFoundError, PermissionError):
                return self.json_reply(403, {"error": "stage prerequisites not satisfied"})
            except Exception:
                # Never leak decryption details in the public HTTP response.
                return self.json_reply(500, {"error": "internal verification error"})

        def log_message(self, fmt, *args):
            # Don't log auth headers or payloads; avoid printing observations.
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("Vault portal listening on local interface:", httpd.server_address)
    httpd.serve_forever()

def main():
    p = argparse.ArgumentParser(description="BEAN blind target commitment and gated reveal")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("directory")
    s = sub.add_parser("serve")
    s.add_argument("directory")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    if args.command == "create":
        pw = getpass.getpass("Vault passphrase (not saved): ")
        confirm = getpass.getpass("Confirm: ")
        if pw != confirm:
            p.error("Passphrases differ")
        print(json.dumps(initialize(Path(args.directory), pw), indent=2))
        print("IMPORTANT: Archive vault.json privately and publish challenge.json commitment before the new chat.")
    else:
        server(Path(args.directory), args.host, args.port)

if __name__ == "__main__":
    main()
