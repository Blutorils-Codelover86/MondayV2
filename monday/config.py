from dataclasses import dataclass, field
from pathlib import Path
import os

@dataclass
class Config:
    roots: tuple[Path, ...] = field(default_factory=lambda: tuple(
        Path(p).expanduser().resolve() for p in os.getenv("MONDAY_ROOTS", ":".join(
            str(Path.home() / x) for x in ("Projects", "Documents", "Downloads"))).split(":") if p))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("MONDAY_DATA_DIR", str(Path.home()/".local/state/monday-v2"))).expanduser())
    denied_tools: tuple[str, ...] = field(default_factory=lambda: tuple(x.strip() for x in os.getenv("MONDAY_DENY_TOOLS", "").split(",") if x.strip()))
    web_fallback: bool = field(default_factory=lambda: os.getenv("MONDAY_WEB_FALLBACK", "1") != "0")
    max_steps: int = 16
    task_timeout: float = 180
    command_timeout: float = 30
    output_limit: int = 16384
    file_limit: int = 131072
    search_provider: str = field(default_factory=lambda: os.getenv("MONDAY_SEARCH_PROVIDER", "auto"))
    search_url: str = field(default_factory=lambda: os.getenv("MONDAY_SEARXNG_URL", ""))
    ollama_model: str = field(default_factory=lambda: os.getenv("MONDAY_MODEL", "gemma3:1b"))
    ollama_url: str = field(default_factory=lambda: os.getenv("MONDAY_OLLAMA_URL", "http://127.0.0.1:11434"))
    laya_path: str = field(default_factory=lambda: os.getenv("MONDAY_LAYA_PATH", ""))

    def public(self):
        return {"web_fallback":self.web_fallback, "denied_tools":list(self.denied_tools), "roots": [str(p) for p in self.roots], "data_dir": str(self.data_dir),
                "max_steps": self.max_steps, "task_timeout": self.task_timeout,
                "local_model": self.ollama_model or "disabled", "laya": bool(self.laya_path),
                "web_search": self.search_url or {"auto":"DuckDuckGo Lite (Wikipedia fallback)","duckduckgo":"DuckDuckGo Lite","wikipedia":"Wikipedia"}.get(self.search_provider,self.search_provider)}
