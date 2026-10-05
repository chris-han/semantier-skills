from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter

from fastapi import HTTPException, Request

from agents.auth_session import request_context_from_request
from agents.auth_db import list_feishu_bot_configs
from . import gateway as meeting_coordinator_gateway
from . import store as meeting_coordinator_store
from .webapi_service import (
    MeetingCoordinatorWebApiCalendarClient,
    MeetingCoordinatorWebApiCronClient,
    meeting_coordinator_delivery_client_from_context,
)

router = APIRouter(tags=["webapi-gateway"])

ROUTE_POLICY_MAP = {
    ("GET", "/system/meeting-coordinator/simulation"): "authenticated",
    ("POST", "/system/meeting-coordinator/state-evolution/runs"): "authenticated",
    ("GET", "/system/meeting-coordinator/state-evolution/runs/{run_id}"): "authenticated",
    ("POST", "/callbacks/feishu/meeting-coordinator/reply"): "public",
    ("GET", "/system/meeting-coordinator/workflow-binding"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/start"): "authenticated",
    ("GET", "/system/meeting-coordinator/monitors"): "authenticated",
    ("GET", "/system/meeting-coordinator/negotiations"): "authenticated",
    ("GET", "/system/meeting-coordinator/negotiations/{negotiation_id}"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/run"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/reply"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/finalize"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/cancel"): "authenticated",
    (
        "POST",
        "/plugins/meeting-coordinator/negotiations/{negotiation_id}/requester-decision",
    ): "authenticated",
    ("GET", "/system/meeting-coordinator/settings"): "authenticated",
    ("PUT", "/system/meeting-coordinator/settings"): "authenticated",
    ("POST", "/system/meeting-coordinator/delivery-tasks/retry"): "authenticated",
    (
        "POST",
        "/system/meeting-coordinator/delivery-tasks/{delivery_task_id}/requeue",
    ): "authenticated",
}

ROUTE_AUTHZ_CLASS_MAP = {}


@router.get('/system/meeting-coordinator/simulation')
async def system_meeting_coordinator_simulation(request: Request, workspace_user_count: int = 4,
                                                stable_seed: str = 'workshop-v1',
                                                workflow_version: str = '2', scenario: str = 'A'):
    from .simulation import simulate_meeting
    from starlette.concurrency import run_in_threadpool
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')
    try:
        return await run_in_threadpool(simulate_meeting, workspace_user_count=workspace_user_count, stable_seed=stable_seed, context=ctx,
                                workflow_version=workflow_version, scenario=scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _create_state_evolution_run(ctx, body):
    import yaml
    from contracts.state_evolution import evolution_hash
    from services.state_evolution_compiler import build_meeting_evolution_binding, compile_meeting_evolution
    from services.state_evolution_service import (
        authenticated_state_evolution_store,
        invoke_state_evolution_worker,
        project_meeting_result,
        seal_evolution_result,
        state_evolution_worker_build_pin,
    )
    session_ref=body.get('sessionRef')
    scenario_id=body.get('scenario','A')
    user_count=body.get('workspaceUserCount',4)
    stable_seed=body.get('stableSeed','workshop-v1')
    if not isinstance(session_ref,str) or not session_ref.strip():
        raise ValueError('SESSION_REF_REQUIRED')
    if scenario_id not in tuple('ABCDEF'):
        raise ValueError('INVALID_SCENARIO')
    if type(user_count) is not int or not 3 <= user_count <= 12:
        raise ValueError('INVALID_WORKSPACE_USER_COUNT')
    if not isinstance(stable_seed,str) or not 1 <= len(stable_seed) <= 128:
        raise ValueError('INVALID_STABLE_SEED')
    with authenticated_state_evolution_store(ctx,session_ref=session_ref,channel='web') as (store,scope,_session_id):
        worker_pin=state_evolution_worker_build_pin()
        resolved=invoke_state_evolution_worker(ctx,'describe-meeting-source',worker_pin=worker_pin)
        native_source=resolved['definition']
        execution=resolved['execution']
        source_path=Path(__file__).with_name('workflows')/'meeting-negotiation.workflow.yaml'
        source=yaml.safe_load(source_path.read_text(encoding='utf-8'))
        profile_root=Path(__file__).with_name('simulation_profiles')
        profile_seeds={name:yaml.safe_load((profile_root/f'{name}.yaml').read_text(encoding='utf-8'))
                       for name in ('requester','cooperative','conflict')}
        from . import simulation as meeting_simulation
        package_root=Path(__file__).resolve().parent
        repo_root=Path(__file__).resolve().parents[3]
        import contracts.state_evolution as evolution_contract
        import services.state_evolution_clock as evolution_clock
        import services.state_evolution_compiler as evolution_compiler
        import services.state_evolution_service as evolution_service
        import agents.meeting_demo_users as meeting_demo_users
        def code_pin(kind,reference,paths,base):
            inventory={str(path.relative_to(base)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted(paths)}
            return {'artifact_kind':kind,'artifact_ref':reference,'artifact_hash':evolution_hash(inventory)}
        producer_paths=sorted(path for path in package_root.rglob('*.py') if 'tests' not in path.parts)+[Path(meeting_demo_users.__file__).resolve()]
        compiler_paths=[Path(module.__file__).resolve() for module in
            (evolution_contract,evolution_compiler,evolution_clock,evolution_service)]
        producer_pin=code_pin('meeting_simulation_producer','feishu-meeting-coordinator:simulation-source',producer_paths,repo_root)
        compiler_pin=code_pin('state_evolution_compiler','semantier:state-evolution-meeting-compiler',compiler_paths,repo_root)
        binding=build_meeting_evolution_binding(scope=scope,source=source,execution=execution,native_source=native_source,
            profile_seeds=profile_seeds,compiler=compiler_pin,backend=worker_pin,producer=producer_pin,
            effective_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
        scenario={'id':scenario_id,'overrides':{'workspace_user_count':user_count,'stable_seed':stable_seed},'scheduledInputs':[]}
        ir,plan=compile_meeting_evolution(binding,source,execution,scenario=scenario,compiler=compiler_pin,
            backend=worker_pin,producer=producer_pin,native_source=native_source)
        trace=meeting_simulation.simulate_meeting(workspace_user_count=user_count,stable_seed=stable_seed,
            workflow_version=str(source['workflow_version']),scenario=scenario_id,context=ctx,
            compiled_program=plan['programs']['workflow'])
        recorded_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        reducer_projection=invoke_state_evolution_worker(ctx,'normalize-meeting-trace',worker_pin=worker_pin,payload={
            'workflowDefinition':native_source,
            'simulationRef':trace['scenarioRef'],'definitionHash':plan['sourceMap']['workflow.run-status']['artifact_hash'],
            'recordedAt':recorded_at,'events':[{'id':step['eventId'],'kind':step['eventType'],'payload':step} for step in trace['steps']]})
        run=project_meeting_result(trace,plan,attempt_id='attempt_'+uuid4().hex,
            recorded_at=recorded_at,reducer_projection=reducer_projection)
        seal_evolution_result(store,ir,plan,run,trusted_scope=scope,resolved_source_pins=ir['sourcePins'],
            trusted_producer=producer_pin)
        return {'ir':ir,'plan':plan,'run':run}


@router.post('/system/meeting-coordinator/state-evolution/runs')
async def system_meeting_coordinator_state_evolution_run(request: Request):
    from agents.auth_session import request_context_from_request
    from starlette.concurrency import run_in_threadpool
    ctx=request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401,detail='authentication required')
    try:
        body=await request.json()
        if not isinstance(body,dict):
            raise ValueError('INVALID_REQUEST')
        return await run_in_threadpool(_create_state_evolution_run,ctx,body)
    except PermissionError as exc:
        raise HTTPException(status_code=403,detail=str(exc)) from exc
    except ValueError as exc:
        message=str(exc)
        status=403 if message.startswith('FORBIDDEN_') else 404 if message=='SESSION_NOT_FOUND' else 422 if message.startswith('INVALID_') or message.endswith('_REQUIRED') else 409
        raise HTTPException(status_code=status,detail=message) from exc


@router.get('/system/meeting-coordinator/state-evolution/runs/{run_id}')
async def system_meeting_coordinator_state_evolution_replay(run_id: str, request: Request, sessionRef: str):
    from agents.auth_session import request_context_from_request
    from services.state_evolution_service import authenticated_state_evolution_store,replay_evolution_run
    from starlette.concurrency import run_in_threadpool
    ctx=request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401,detail='authentication required')
    def replay():
        with authenticated_state_evolution_store(ctx,session_ref=sessionRef,channel='web') as (store,scope,_session_id):
            return replay_evolution_run(store,run_id,trusted_scope=scope)
    try:
        return await run_in_threadpool(replay)
    except PermissionError as exc:
        raise HTTPException(status_code=403,detail=str(exc)) from exc
    except ValueError as exc:
        message=str(exc)
        status=403 if message.startswith('FORBIDDEN_') else 404 if message in {'SESSION_NOT_FOUND','EVOLUTION_MISSING_ARTIFACT'} else 409
        raise HTTPException(status_code=status,detail=message) from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nested_text(payload: dict[str, Any], *path: str) -> str:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _text(current)


def _feishu_callback_app_id(payload: dict[str, Any]) -> str:
    return (
        _nested_text(payload, "header", "app_id")
        or _nested_text(payload, "event", "app_id")
        or _text(payload.get("app_id"))
    )


def _feishu_callback_sender_open_id(payload: dict[str, Any]) -> str:
    return (
        _nested_text(payload, "event", "sender", "sender_id", "open_id")
        or _nested_text(payload, "event", "sender", "open_id")
        or _nested_text(payload, "sender", "sender_id", "open_id")
        or _text(payload.get("sender_open_id"))
    )


def _feishu_callback_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if isinstance(message, dict):
        return message
    event = payload.get("event")
    event_message = event.get("message") if isinstance(event, dict) else None
    return event_message if isinstance(event_message, dict) else {}


def _feishu_callback_raw_text(payload: dict[str, Any]) -> str:
    message = _feishu_callback_message(payload)
    raw = message.get("content") or payload.get("raw_text") or payload.get("text") or ""
    if isinstance(raw, dict):
        raw = raw.get("text") or ""
    return str(raw).replace("\x00", "").strip()[:4000]


def _feishu_workspace_config_for_app_id(app_id: str) -> dict[str, Any] | None:
    for config in list_feishu_bot_configs():
        if _text(config.get("app_id")) != app_id:
            continue
        workspace_id = _text(
            config.get("owner_workspace_id") or config.get("workspace_id")
        )
        if workspace_id:
            return {**config, "workspace_id": workspace_id}
    return None


def _verify_feishu_callback_signature(
    request: Request,
    *,
    raw_body: bytes,
    config: dict[str, Any],
) -> bool:
    signature = _text(request.headers.get("x-feishu-signature"))
    timestamp = _text(request.headers.get("x-feishu-request-timestamp"))
    nonce = _text(request.headers.get("x-feishu-request-nonce"))
    app_secret = _text(config.get("app_secret"))
    if not signature or not timestamp or not nonce or not app_secret:
        return False
    signed = timestamp.encode("utf-8") + b"." + nonce.encode("utf-8") + b"." + raw_body
    expected = hmac.new(app_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _require_negotiation_operator(negotiation: dict, *, user_id: str | None) -> None:
    if str(negotiation.get("creator_user_id") or "") != str(user_id or ""):
        raise HTTPException(status_code=403, detail="requester_or_operator_required")


@router.post("/callbacks/feishu/meeting-coordinator/reply")
async def feishu_meeting_coordinator_reply_callback(request: Request):
    raw_body = await request.body()
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid_json")
    app_id = _feishu_callback_app_id(body)
    if not app_id:
        raise HTTPException(status_code=400, detail="missing_app_id")
    config = _feishu_workspace_config_for_app_id(app_id)
    if config is None:
        raise HTTPException(status_code=403, detail="unknown_tenant")
    if not _verify_feishu_callback_signature(request, raw_body=raw_body, config=config):
        raise HTTPException(status_code=403, detail="invalid_signature")
    message = _feishu_callback_message(body)
    envelope = {
        "callback_origin": True,
        "workspace_id": str(config["workspace_id"]),
        "feishu_app_id": app_id,
        "callback_signature_valid": True,
        "sender_open_id": _feishu_callback_sender_open_id(body),
        "provider_message_id": _text(
            message.get("message_id") or body.get("provider_message_id")
        ),
        "thread_id": _text(message.get("thread_id") or body.get("thread_id")),
        "root_message_id": _text(
            message.get("root_id")
            or message.get("parent_id")
            or body.get("root_message_id")
        ),
        "received_at_utc": _utc_now_iso(),
        "raw_text": _feishu_callback_raw_text(body),
        "payload": {
            "event_type": _nested_text(body, "header", "event_type")
            or _text(body.get("type")),
            "message_type": _text(message.get("message_type")),
        },
    }
    try:
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            envelope,
            store=meeting_coordinator_store.store_for_workspace(str(config['workspace_id'])),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=403, detail="uncorrelated_message") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(result, dict) and result.get("status") in {
        "not_correlated",
        "rejected",
    }:
        raise HTTPException(
            status_code=403,
            detail=result.get("reason", "uncorrelated_message"),
        )
    return {"ok": True, "result": result}


@router.get("/system/meeting-coordinator/monitors")
async def system_meeting_coordinator_monitors(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.store_for_context(ctx)
    meeting_coordinator_gateway.repair_delivery_retry_scheduler(
        workspace_id=ctx.workspace_id,
        store=store,
        cron=MeetingCoordinatorWebApiCronClient(ctx),
    )
    return {
        "ok": True,
        "monitors": store.list_operation_monitors(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
        "deliveryTasks": store.list_operation_delivery_tasks(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
        "scheduler": store.get_workspace_state(ctx.workspace_id),
    }


@router.get("/system/meeting-coordinator/workflow-binding")
async def system_meeting_coordinator_workflow_binding(request: Request):
    from contracts.workflow_execution import read_active_meeting_binding
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')
    try:
        return read_active_meeting_binding(ctx)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/system/meeting-coordinator/negotiations/start")
async def system_meeting_coordinator_negotiation_start(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')
    body = await request.json()
    try:
        store = meeting_coordinator_store.store_for_context(ctx)
        result = meeting_coordinator_gateway.negotiation_case_start(
            body,
            store=store,
            cron=MeetingCoordinatorWebApiCronClient(ctx),
            runtime_context=ctx,
        )
        return {'ok': True, 'negotiation':result}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/system/meeting-coordinator/negotiations")
async def system_meeting_coordinator_negotiations(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.store_for_context(ctx)
    return {
        "ok": True,
        "negotiations": store.list_operation_negotiations(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
    }


@router.get("/system/meeting-coordinator/negotiations/{negotiation_id}")
async def system_meeting_coordinator_negotiation_detail(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    workflow_execution = None
    if negotiation.get('workflow_binding_json'):
        if negotiation.get('organization_id') != ctx.organization_id:
            raise HTTPException(status_code=404, detail='not_found_or_wrong_workspace')
        try:
            workflow_execution = store.read_workflow_execution(negotiation_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "workflow_execution": workflow_execution,
        "negotiation": negotiation,
        "participants": store.list_negotiation_participants(negotiation_id),
        "candidate_slots": store.list_candidate_slots(negotiation_id),
        "votes": store.list_negotiation_votes(negotiation_id),
        "messages": store.list_negotiation_messages(negotiation_id),
        "finalize_attempts": store.list_finalize_attempts(negotiation_id),
        "events": store.list_negotiation_events(negotiation_id),
    }


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/run")
async def system_meeting_coordinator_negotiation_run(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    try:
        negotiation = meeting_coordinator_gateway.ensure_negotiation_kanban_task(
            negotiation_id=negotiation_id,
            store=store,
            kanban=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "negotiation": negotiation}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/reply")
async def system_meeting_coordinator_negotiation_reply(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    participant_user_id = str(
        body.get("participant_user_id") or ctx.user_id or ""
    ).strip()
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    if negotiation["status"] not in {
        "pending_decliner_input",
        "collecting_votes",
        "awaiting_requester_decision",
    }:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id or "unknown",
            message_id=str(body.get("message_id") or ""),
            reason="non_reply_accepting_state",
        )
        raise HTTPException(status_code=409, detail="non_reply_accepting_state")
    participants = store.list_negotiation_participants(negotiation_id)
    if participant_user_id not in {
        str(item["attendee_user_id"]) for item in participants
    }:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id or "unknown",
            message_id=str(body.get("message_id") or ""),
            reason="unknown_sender",
        )
        raise HTTPException(status_code=403, detail="not_authorized")
    callback_origin = bool(
        body.get("callback_origin") or "callback_signature_valid" in body
    )
    outbound_message_event_id = str(body.get("outbound_message_event_id") or "").strip()
    message_id = str(body.get("message_id") or "").strip()
    if callback_origin and body.get("callback_signature_valid") is not True:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id,
            message_id=message_id,
            reason="invalid_signature",
        )
        raise HTTPException(status_code=403, detail="invalid_signature")
    if callback_origin:
        try:
            outbound = store.get_negotiation_message(outbound_message_event_id)
        except KeyError as exc:
            store.record_inbound_reply_rejected(
                negotiation_id=negotiation_id,
                participant_user_id=participant_user_id,
                message_id=message_id,
                reason="uncorrelated_message",
            )
            raise HTTPException(status_code=403, detail="uncorrelated_message") from exc
        if (
            outbound["negotiation_id"] != negotiation_id
            or outbound["participant_user_id"] != participant_user_id
            or outbound["direction"] != "outbound"
        ):
            store.record_inbound_reply_rejected(
                negotiation_id=negotiation_id,
                participant_user_id=participant_user_id,
                message_id=message_id,
                reason="uncorrelated_message",
            )
            raise HTTPException(status_code=403, detail="uncorrelated_message")
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            {
                **body,
                "negotiation_id": negotiation_id,
                "participant_user_id": participant_user_id,
                "message_id": message_id,
            },
            store=store,
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
        return {
            "ok": True,
            "result": result,
        }
    try:
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            {
                **body,
                "negotiation_id": negotiation_id,
                "participant_user_id": participant_user_id,
                "message_id": message_id,
            },
            store=store,
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/finalize")
async def system_meeting_coordinator_negotiation_finalize(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    if body.get("requester_confirmation") is not True:
        raise HTTPException(status_code=403, detail="requester_confirmation_required")
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
        _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
        result = meeting_coordinator_gateway.finalize_negotiation_case(
            {
                **body,
                "negotiation_id": negotiation_id,
                "requested_by_user_id": str(ctx.user_id or ""),
            },
            store=store,
            calendar_client=MeetingCoordinatorWebApiCalendarClient(ctx),
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "result": result, "finalize_attempt": result["attempt"]}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/cancel")
async def system_meeting_coordinator_negotiation_cancel(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    owner = f"operator:{ctx.user_id or 'unknown'}"
    result = store.transition_negotiation_state(
        negotiation_id,
        expected_state=str(negotiation_record["status"]),
        next_state="cancelled",
        patch={},
        actor_id=owner,
    )
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=str(result["reason"]))
    meeting_coordinator_gateway.complete_negotiation_kanban_if_terminal(
        negotiation_id=negotiation_id,
        store=store,
        kanban=None,
        summary="Operator cancelled the meeting time negotiation.",
    )
    return {"ok": True, "negotiation": result["record"]}


@router.post(
    "/plugins/meeting-coordinator/negotiations/{negotiation_id}/requester-decision"
)
async def plugins_meeting_coordinator_negotiation_requester_decision(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    action = str(body.get("action") or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    store = meeting_coordinator_store.store_for_context(ctx)
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
            organization_id=ctx.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    if action == "requester_select_slot" and not (
        str(body.get("slot_id") or body.get("selected_slot_id") or "").strip()
    ):
        raise HTTPException(
            status_code=400, detail="selected_slot_id is required for requester_select_slot"
        )
    try:
        result = meeting_coordinator_gateway.apply_requester_decision(
            {
                **body,
                "negotiation_id": negotiation_id,
                "requested_by_user_id": str(ctx.user_id or ""),
            },
            store=store,
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@router.get("/system/meeting-coordinator/settings")
async def system_meeting_coordinator_settings(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    state = meeting_coordinator_store.store_for_context(ctx).get_workspace_state(
        ctx.workspace_id
    )
    return {
        "ok": True,
        "settings": {
            "max_followups": int(state.get("max_followups") or 3),
        },
    }


@router.put("/system/meeting-coordinator/settings")
async def system_meeting_coordinator_settings_update(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    try:
        max_followups = int(body.get("max_followups"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="max_followups must be an integer"
        ) from exc
    try:
        state = meeting_coordinator_store.store_for_context(ctx).update_workspace_settings(
            ctx.workspace_id,
            max_followups=max_followups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "settings": {
            "max_followups": int(state.get("max_followups") or 3),
        },
    }


@router.post("/system/meeting-coordinator/delivery-tasks/retry")
async def system_meeting_coordinator_delivery_retry(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    result = meeting_coordinator_gateway.escalation_retry_tick(
        {"workspace_id": ctx.workspace_id},
        store=meeting_coordinator_store.store_for_context(ctx),
        delivery_client=meeting_coordinator_delivery_client_from_context(ctx),
    )
    return {"ok": True, **result}


@router.post("/system/meeting-coordinator/delivery-tasks/{delivery_task_id}/requeue")
async def system_meeting_coordinator_delivery_task_requeue(
    delivery_task_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    task = meeting_coordinator_gateway.requeue_delivery_task(
        delivery_task_id=delivery_task_id,
        reason=reason,
        store=meeting_coordinator_store.store_for_context(ctx),
        cron=MeetingCoordinatorWebApiCronClient(ctx),
    )
    return {"ok": True, "delivery_task": task}
