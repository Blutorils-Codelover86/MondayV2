import os, re
from pathlib import Path
from .models import Risk, Observation
from .runtime import Cancelled

class PathPolicy:
    forbidden = {".ssh", ".gnupg", ".aws", ".config", ".local", ".git", "node_modules", ".venv", "__pycache__"}
    def __init__(self, roots): self.roots = tuple(Path(p).resolve() for p in roots)
    def resolve(self, value, mutation=False):
        raw = Path(value).expanduser().absolute()
        # Reject symlinks in every component, even when the resolved target remains inside.
        if any(p.is_symlink() for p in (raw, *raw.parents)): raise PermissionError("Symlinks are not allowed")
        path = raw.resolve()
        if not any(path.is_relative_to(r) for r in self.roots): raise PermissionError("Path is outside configured roots")
        if any(x in self.forbidden or x == ".env" or x.startswith(".env.") for x in path.parts):
            raise PermissionError("Private or generated path is protected")
        if mutation and path in self.roots: raise PermissionError("Cannot mutate a root directory")
        return path

class CommandPolicy:
    # Exact read-only shapes. Builds are offered through project.run, not this escape hatch.
    allowed = {("uname", "-a"), ("uptime",), ("df", "-h"), ("free", "-m"), ("ip", "-brief", "address"), ("rfkill", "list")}
    def validate(self, argv):
        if not isinstance(argv, list) or not all(isinstance(x,str) for x in argv): raise PermissionError("Use an argv list")
        if tuple(argv) not in self.allowed: raise PermissionError("Command is not an approved diagnostic template")
        return argv

class ActionGateway:
    def __init__(self, registry, runtime, audit, approve=None, dry_run=False):
        self.registry, self.runtime, self.audit = registry, runtime, audit
        self.approve = approve or (lambda _:False)
        self.dry_run = dry_run
        self.paths = PathPolicy(runtime.cfg.roots)
        self.commands = CommandPolicy()

    def risk(self, action):
        tool = self.registry.validate(action.tool, action.arguments)
        args = action.arguments
        for key in ("path", "source", "destination", "cwd"):
            if key in args:
                self.paths.resolve(args[key], mutation=tool.risk >= Risk.MEDIUM and action.tool.startswith("fs."))
        if action.tool == "command.run": self.commands.validate(args["argv"])
        if action.tool == "process.terminate" and "pid" in args:
            if args["pid"] <= 1 or args["pid"] == os.getpid(): raise PermissionError("Protected process")
        if action.tool == "fs.delete": return Risk.CRITICAL
        return tool.risk

    def perform(self, action):
        args = {k:v for k,v in action.arguments.items() if k not in ("content", "text")}
        try:
            self.runtime.check()
            risk = self.risk(action)
            tool = self.registry.get(action.tool)
            self.audit.emit("proposal", tool=action.tool, arguments=args, risk=risk.name)
            if self.dry_run:
                self.audit.emit("dry_run", tool=action.tool)
                return Observation(action.tool, True, {"risk":risk.name, "arguments":args}, simulated=True)
            if risk >= Risk.MEDIUM:
                detail = tool.approval_detail(action.arguments) if tool.approval_detail else ""
                if "content" in action.arguments:
                    content=action.arguments["content"]
                    detail += f" Writes {len(content.encode())} bytes: {content[:120]!r}."
                prompt = f"{action.tool} {args} ({risk.name}). {detail} Approve? [y/N]"
                accepted = self.approve(prompt) is True
                self.audit.emit("approval", tool=action.tool, approved=accepted, arguments=args)
                if not accepted: return Observation(action.tool, False, error="Approval denied", data={"status":"CANCELLED"})
            self.runtime.check()
            # Validate a second time after the approval wait.
            self.risk(action)
            result = tool.execute(**action.arguments)
            self.runtime.check()
            verified = bool(tool.verify(action.arguments, result)) if tool.verify else True
            inverse = result.pop("_inverse", None) if isinstance(result,dict) else None
            if not verified: inverse = None
            self.audit.emit("result", tool=action.tool, verified=verified)
            return Observation(action.tool, verified, result, "" if verified else "Verification failed", verified, inverse=inverse)
        except Cancelled as e:
            self.audit.emit("cancelled", tool=action.tool)
            return Observation(action.tool, False, error=str(e), data={"status":"CANCELLED"})
        except PermissionError as e:
            self.audit.emit("blocked", tool=action.tool, error=str(e))
            return Observation(action.tool, False, error=f"Policy blocked the action: {e}", data={"status":"BLOCKED"})
        except Exception as e:
            self.audit.emit("failure", tool=action.tool, error=f"{type(e).__name__}: {e}")
            return Observation(action.tool, False, error=f"{type(e).__name__}: {e}")
