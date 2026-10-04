import os
import sys
import pkgutil
import logging
import importlib
import inspect
from typing import Dict, Type, List

from beaver_agent.agent import Agent

logger = logging.getLogger(__name__)

_AGENT_CACHE: Dict[str, Type[Agent]] = {}
_DIR_MTIME = None

def discover_expert_agents() -> Dict[str, Type[Agent]]:
    base_dir = os.path.dirname(__file__)
    pkg_name = __package__ or os.path.basename(base_dir)
    if not __package__:
        src_dir = os.path.dirname(base_dir)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
    agents: Dict[str, Type[Agent]] = {}
    for modinfo in pkgutil.iter_modules([base_dir]):
        name = modinfo.name
        if not name.endswith("_agent") or name in ("agent", "main_agent"):
            continue
        try:
            module = importlib.import_module(f".{name}", __package__) if __package__ else importlib.import_module(f"{pkg_name}.{name}")
        except Exception as e:
            # A single broken expert-agent module (e.g. one just written by
            # CreatorAgent) must not take down the whole registry: the main
            # agent's call_agent enum is built from it.
            logger.warning("skipping expert agent module %s: %s", name, e)
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Agent) and obj is not Agent and obj.__module__ == module.__name__:
                key = name[:-len("_agent")]
                agents[key] = obj
                break
    return agents

def _maybe_refresh_cache(force: bool = False) -> None:
    global _AGENT_CACHE, _DIR_MTIME
    base_dir = os.path.dirname(__file__)
    mtime = None
    try:
        mtime = os.path.getmtime(base_dir)
    except Exception:
        pass
    if force or (_DIR_MTIME != mtime):
        importlib.invalidate_caches()
        _AGENT_CACHE = discover_expert_agents()
        _DIR_MTIME = mtime

def get_expert_agent_names() -> List[str]:
    _maybe_refresh_cache()
    return sorted(_AGENT_CACHE.keys())

def create_expert_agent(agent_name: str) -> Agent:
    _maybe_refresh_cache()
    cls = _AGENT_CACHE.get(agent_name)
    if not cls:
        raise ValueError(f"Unknown expert agent: {agent_name}")
    return cls()

def get_expert_agent_docs() -> Dict[str, str]:
    _maybe_refresh_cache()
    docs: Dict[str, str] = {}
    for name, cls in _AGENT_CACHE.items():
        doc = (cls.__doc__ or "").strip()
        docs[name] = doc
    return docs

if __name__ == "__main__":
    print(get_expert_agent_names())
    print(get_expert_agent_docs())