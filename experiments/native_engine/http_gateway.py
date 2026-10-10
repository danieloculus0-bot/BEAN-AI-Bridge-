"""Experimental BEAN Native symbolic inference HTTP service.

Local-only subset of Ollama's HTTP API, not a general neural LLM runtime.
Never uses untrusted model prose as a canonical fact.
"""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

from ezbean.knowledge_gate import DefinitionLibrary,OutputGate
from experiments.native_engine.native_lab import Gateway, Provider, Blueprint

VERSION="bean-native-symbolic-lab009"
MODEL="bean-native:symbolic"

def prepare_request(payload):
    if not isinstance(payload,dict): raise ValueError("Request must be an object")
    if payload.get("model",MODEL)!=MODEL: raise ValueError("Only bean-native:symbolic supported")
    messages=payload.get("messages")
    if not isinstance(messages,list) or not messages or not isinstance(messages[-1],dict):
        raise ValueError("messages must be a nonempty array")
    content=messages[-1].get("content")
    if not isinstance(content,str): raise ValueError("last message content must be text")
    try:
        query=json.loads(content)
    except json.JSONDecodeError:
        raise ValueError('Send JSON content with "concept" and "as_of_utc" keys') from None
    if not isinstance(query,dict): raise ValueError("content JSON must be object")
    concept=query.get("concept")
    at=query.get("as_of_utc")
    if not isinstance(concept,str) or not isinstance(at,str):
        raise ValueError("concept and as_of_utc are required strings")
    return concept,at

def serve(library:DefinitionLibrary,blueprint=Blueprint(True,False,False,False),
          host="127.0.0.1",port=11435,provider=None):
    if host not in {"127.0.0.1","localhost","::1"}:
        raise ValueError("BEAN Native prototype is loopback only")
    gateway=Gateway(library,provider or Provider())
    class Handler(BaseHTTPRequestHandler):
        def send_json(self,code,payload):
            raw=json.dumps(payload,ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path=="/api/version":
                return self.send_json(200,{"version":VERSION,"engine":"native symbolic knowledge gateway"})
            if self.path=="/api/tags":
                return self.send_json(200,{"models":[{"name":MODEL,"model":MODEL,
                    "details":{"family":"symbolic_registry_not_neural"}}]})
            return self.send_json(404,{"error":"unsupported endpoint"})
        def do_POST(self):
            if self.path!="/api/chat":
                return self.send_json(404,{"error":"unsupported endpoint"})
            if int(self.headers.get("Content-Length","0"))>16000:
                return self.send_json(413,{"error":"payload too large"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(length))
                concept,at=prepare_request(payload)
                start=time.perf_counter_ns()
                outcome=gateway.run(blueprint,concept,at)
                # Preserve the same shape for accepted answers and failed gates;
                # rejected outputs are omitted, never replaced with model prose.
                result={"model":MODEL,
                    "created_at":datetime.now(timezone.utc).isoformat(),
                    "message":{"role":"assistant",
                               "content":outcome.get("output") or ""},
                    "done":True,"done_reason":"stop",
                    "total_duration":time.perf_counter_ns()-start,
                    "verification":{"accepted":bool(outcome.get("accepted")),
                        "reason":outcome.get("reason"),"stages":outcome["stages"],
                        "definition_id":outcome.get("definition_id")}}
                self.send_json(200,result)
            except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
                self.send_json(400,{"error":str(exc)[:180]})
            except Exception as exc:
                self.send_json(500,{"error":"Gateway error: "+type(exc).__name__})
        def log_message(self,format,*args):
            pass
    return ThreadingHTTPServer((host,port),Handler)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",type=Path,required=True,
                        help="Persistent SQLite DB containing curated definitions")
    parser.add_argument("--port",type=int,default=11435)
    args=parser.parse_args()
    if args.port<=0 or args.port>65535: parser.error("port out of range")
    library=DefinitionLibrary(args.database)
    server=serve(library,host="127.0.0.1",port=args.port)
    print(f"{VERSION} localhost:{args.port} (restricted symbolic library only)",flush=True)
    try:server.serve_forever()
    finally:
        server.server_close()
        library.close()

if __name__=="__main__":main()
