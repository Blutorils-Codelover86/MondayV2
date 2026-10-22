from .config import Config
from .audit import Audit
from .runtime import Runtime
from .registry import ToolRegistry, Tool
from .models import Risk
from .safety import ActionGateway
from .system import System
from .filesystem import Filesystem
from .desktop import DesktopController
from .projects import Projects
from .packages import Packages
from .web import WebTools
from .providers import OllamaReasoner, LayaProvider
from .engine import DecisionEngine, Agent

def build(cfg=None,approve=None,dry_run=False):
    cfg=cfg or Config(); audit=Audit(cfg.data_dir); runtime=Runtime(cfg)
    registry=ToolRegistry(); fs=Filesystem(cfg,runtime); desktop=DesktopController(runtime)
    system=System(runtime); projects=Projects(cfg,runtime,fs,desktop); packages=Packages(runtime)
    web=WebTools(runtime,cfg,desktop)
    for group in (system,fs,desktop,projects,packages,web): group.register(registry)
    registry.register(Tool('command.run','Run an exact approved diagnostic argv template',{'argv':{'type':list},'cwd':{'type':str,'required':False}},Risk.READ_ONLY,
                           lambda argv,cwd=None:runtime.run(argv,cwd),lambda a,d:d['exit_code']==0))
    gateway=ActionGateway(registry,runtime,audit,approve,dry_run)
    reasoner=OllamaReasoner(cfg) if cfg.ollama_model else None
    engine=DecisionEngine(cfg,registry,reasoner,LayaProvider(cfg,runtime) if cfg.laya_path else None)
    return Agent(engine,gateway,audit)
