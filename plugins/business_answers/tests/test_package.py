import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys


def test_registered_tools_share_native_adapter():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('business_answers_test_package', root / '__init__.py', submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    calls = []
    module.register(SimpleNamespace(register_tool=lambda **kwargs: calls.append(kwargs), register_skill=lambda **kwargs: None))
    assert {item['name'] for item in calls} == set(module.schemas.TOOL_SCHEMAS)
    assert {item['toolset'] for item in calls} == {'business_answers'}
    source = (root / 'tools.py').read_text()
    assert 'from agents import business_answers' in source
    assert 'sqlite' not in source and 'duckdb' not in source
