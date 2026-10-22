from pathlib import Path
import json, os, time, uuid
from dataclasses import asdict
from .redact import redact

class Audit:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "audit.jsonl"

    def emit(self, kind, **values):
        row = redact({"time": time.time(), "kind": kind, **values})
        # Content is omitted: task records retain decisions and evidence, not private file bodies.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def save(self, state):
        ident = uuid.uuid4().hex
        record = redact(asdict(state))
        for o in record["observations"]:
            if o["tool"] in ("fs.read", "fs.write", "fs.create", "desktop.clipboard_read"):
                o["data"] = "[content omitted]"
        for d in record["decisions"]:
            d["current_state"] = {"observation_count": len(d["current_state"].get("observations", []))}
            if d.get("next_action"):
                d["next_action"]["arguments"].pop("content", None)
        action = record.get("context", {}).get("action")
        if isinstance(action,dict):
            contains_body=any(key in action.get("arguments",{}) for key in ("content","text"))
            for key in ("content","text"): action.get("arguments",{}).pop(key,None)
            if contains_body:
                record["objective"]=action["tool"]+" "+json.dumps(action["arguments"])+" [content omitted]"
                for d in record["decisions"]: d["objective"]=record["objective"]
        if any(o["tool"] in ("fs.read","desktop.clipboard_read") for o in record["observations"]):
            record["response"] = "[private content omitted]"
            for d in record["decisions"]:
                if d.get("response"): d["response"]="[private content omitted]"
        record["id"] = ident
        fd = os.open(self.directory / (ident + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, default=str, indent=2)
        self.emit("task", id=ident, status=state.status, response=record["response"])
        return ident

    def history(self, limit=10):
        files = sorted(self.directory.glob("*.json"), key=lambda p:p.stat().st_mtime, reverse=True)
        return [json.loads(p.read_text()) for p in files[:limit]]
