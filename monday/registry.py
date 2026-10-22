from dataclasses import dataclass
from typing import Callable
from .models import Risk

@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    risk: Risk
    execute: Callable
    verify: Callable | None = None
    approval_detail: Callable | None = None

class ToolRegistry:
    def __init__(self): self._tools = {}
    def register(self, tool):
        if tool.name in self._tools: raise ValueError("Duplicate tool")
        if tool.risk > Risk.READ_ONLY and tool.verify is None:
            raise ValueError("Mutating tools need a verifier")
        self._tools[tool.name] = tool
    def get(self, name):
        if name not in self._tools: raise ValueError("Unknown tool: " + name)
        return self._tools[name]
    def describe(self):
        types={str:'string',int:'integer',float:'number',bool:'boolean',list:'array',dict:'object'}
        rows=[]
        for t in self._tools.values():
            properties={k:{'type':types[v['type']], **({'enum':v['enum']} if 'enum' in v else {})} for k,v in t.schema.items()}
            rows.append({'name':t.name,'description':t.description,'risk':t.risk.name,
                         'schema':{'type':'object','properties':properties,'required':[k for k,v in t.schema.items() if v.get('required',True)],'additionalProperties':False}})
        return rows
    def validate(self, name, args):
        tool = self.get(name)
        if not isinstance(args, dict): raise ValueError("Arguments must be an object")
        schema = tool.schema
        if set(args) - set(schema): raise ValueError("Unknown argument")
        for key, rule in schema.items():
            if key not in args:
                if rule.get("required", True): raise ValueError("Missing argument: " + key)
                continue
            val = args[key]
            typ = rule["type"]
            if not isinstance(val, typ) or isinstance(val, bool) and typ is int:
                raise ValueError("Wrong argument type: " + key)
            if "enum" in rule and val not in rule["enum"]: raise ValueError("Invalid " + key)
            if isinstance(val, str) and (len(val)>131072 or "\x00" in val): raise ValueError("Invalid string")
        return tool
