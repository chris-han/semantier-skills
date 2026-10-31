"""Retired scheduler entry points cannot be discovered by a fresh plugin host."""
from feishu_meeting_coordinator import register


def test_registration_keeps_business_tools_without_native_scheduler():
    class Context:
        def __init__(self): self.tools = {}
        def register_tool(self, **kw): self.tools[kw['name']] = kw
        def register_cli_command(self, **kw): pass
        def register_skill(self, **kw): pass
    ctx = Context()
    register(ctx)
    assert {'feishu_meeting_negotiation_case_start', 'feishu_meeting_requester_decision',
            'feishu_meeting_negotiation_case_stop', 'feishu_meeting_create'} <= ctx.tools.keys()
    assert not any('cron' in name or name in {'feishu_meeting_escalation_retry_tick',
        'feishu_meeting_delivery_task_requeue'} for name in ctx.tools)


def test_old_scheduler_routes_absent_and_core_projection_retained():
    from feishu_meeting_coordinator.webapi import router, task_runtime_router
    paths = {r.path for r in router.routes}
    assert '/system/meeting-coordinator/monitors' not in paths
    assert not any('/delivery-tasks/' in path for path in paths)
    assert '/api/workflows/feishu-meeting-coordinator/instances/{negotiation_id}' in {r.path for r in task_runtime_router.routes}
