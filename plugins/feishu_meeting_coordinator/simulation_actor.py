"""One workspace-local deterministic actor; JSON Feishu envelopes are its only API."""
from __future__ import annotations
import json
import math
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys

from agents.governed_tool_context import resolve_authenticated_tool_context


def requester_command(ctx, state, command, state_path):
    from . import store as store_module
    from .store import store_for_context
    from .gateway import _refresh_decision_frontier, apply_requester_decision
    store_module.utc_now_iso = lambda: command.get('clockAt','2026-10-05T00:00:00Z')
    db = store_for_context(ctx)
    operation = command['operation']
    if operation == 'initialize_negotiation':
        participants = command['participants']
        binding = {'workspace_owner_id': ctx.workspace_id, 'creator_user_id': ctx.user_id, 'platform': 'feishu',
                   'chat_id': 'simulation-chat', 'thread_id': None, 'session_id': state['sessionRef'],
                   'session_key': state['sessionRef'], 'hermes_home': str(ctx.hermes_home),
                   'delivery_adapter_key': None, 'source': 'simulation_fixture', 'captured_at': command.get('clockAt','2026-10-05T00:00:00Z')}
        monitor = db.start_monitor({'workspace_id': ctx.workspace_id, 'creator_user_id': ctx.user_id,
            'event_id': command['scenarioRef'], 'event_revision_id': 'simulation-revision:1', 'calendar_id': 'simulation-calendar',
            'creator_delivery_binding': binding, 'meeting_title': 'Synthetic meeting', **state['slots']['original'],
            'attendees': [{'user_id': p['userRef'], 'message_user_id': p['userRef'], 'display_name': p['label']} for p in participants]})
        db.update_attendee_statuses(monitor['monitor_id'], [{'user_id': ctx.user_id, 'response_status':
            'accepted' if state['availability']['original'] == 'AVAILABLE' else 'declined'}])
        case = db.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'], event_revision_id='simulation-revision:1',
            trigger_attendee_user_id=participants[2]['userRef'], session_id=state['sessionRef'])
        state.update(caseId=case['negotiation_id'], monitorId=monitor['monitor_id'], knownEvidence=[], slotIds={})
        # Declared synthetic input policy, confined to this disposable domain fixture.
        with db._connect() as conn:
            for p in participants[1:]:
                conn.execute('UPDATE meeting_time_negotiation_participants SET required_for_consent=? WHERE negotiation_id=? AND attendee_user_id=?',
                             (int(p['required']), state['caseId'], p['userRef']))
            if command['scenario'] == 'F':
                conn.execute('UPDATE meeting_time_negotiations SET payload_json=? WHERE negotiation_id=?',
                             (json.dumps({'meeting_necessity': 'RESOLVED_ASYNCHRONOUSLY'}), state['caseId']))
        for subject in ('alternative', 'blocked', 'dominated'):
            slot = state['slots'][subject]
            stored = db.add_candidate_slot(state['caseId'], proposed_by_user_id=ctx.user_id, round_number=1,
                start_time=slot['start_time'], end_time=slot['end_time'], timezone_name='UTC', source_text='Synthetic requester candidate')
            state['slotIds'][subject] = stored['slot_id']
        result = {'caseRef': state['caseId']}
    elif operation == 'receive_feishu':
        message = command['message']
        if message['toWorkspaceRef'] != ctx.workspace_id or message['toUserRef'] != ctx.user_id:
            raise PermissionError('SIMULATION_TRANSPORT_WRONG_RECIPIENT')
        facts = message['facts']; subject = facts['subjectRef']; status = facts['availability']
        db.record_inbound_reply_accepted(negotiation_id=state['caseId'], participant_user_id=message['fromUserRef'],
            message_id=message['messageRef'], message_type='simulation_feishu_response', payload=message)
        if subject == 'original':
            db.update_attendee_statuses(state['monitorId'], [{'user_id': message['fromUserRef'], 'response_status':
                'accepted' if status == 'AVAILABLE' else 'declined' if status == 'UNAVAILABLE' else 'unknown'}])
        elif status != 'UNKNOWN':
            db.record_vote(negotiation_id=state['caseId'], slot_id=state['slotIds'][subject],
                           attendee_user_id=message['fromUserRef'], vote='yes' if status == 'AVAILABLE' else 'no')
        state['knownEvidence'].append({'messageRef': message['messageRef'], 'userRef': message['fromUserRef'],
                                      'workspaceRef': message['fromWorkspaceRef'], **facts})
        result = {'knownEvidence': state['knownEvidence']}
    elif operation == 'planner_tick':
        from .decision_planning import project_decision_frontier
        frontier = _refresh_decision_frontier(state['caseId'], store=db)
        event = next(e for e in reversed(db.list_negotiation_events(state['caseId'])) if e['event_type'] == 'DECISION_FRONTIER_COMPUTED')
        result = {'decision': project_decision_frontier(frontier), 'sourceEventRef': event['event_id'],
                  'slotSubjects': {slot_id: subject for subject, slot_id in state['slotIds'].items()},
                  **({'sourceEventCreatedAt':event['created_at']} if 'clockAt' in command else {})}
    elif operation == 'prepare_wait':
        from agents.durable_responsibility import TIMER, WAIT_EXTERNAL
        from .durable_runtime import MeetingResponsibilityRuntime
        from .gateway import _register_followup_timer
        runtime = MeetingResponsibilityRuntime(store=db, cron=None)
        item = runtime.ensure(state['caseId'])
        claim = runtime.responsibilities.claim(responsibility_id=item.responsibility_id, owner_id='simulation-requester')
        timer = _register_followup_timer(negotiation_id=state['caseId'], store=db, scheduled_at=state['timerDeadlineAt'] if 'clockAt' in command else '2026-10-05T00:00:20Z')
        wait = runtime.responsibilities.register_wait(claim, kind=TIMER, source_ref=timer.timer_id,
            correlation_key=state['caseId'], lifecycle_state=WAIT_EXTERNAL, continuation_disposition=WAIT_EXTERNAL,
            deadline_at=timer.scheduled_at, session_ref=state['sessionRef'])
        runtime._record_waiting(negotiation_id=state['caseId'], responsibility_id=item.responsibility_id)
        state.update(responsibilityRef=item.responsibility_id, timerRef=timer.timer_id)
        result = {'waitRef': wait.wait_id, 'responsibilityRef': item.responsibility_id, 'timerRef': timer.timer_id, 'deadlineAt':timer.scheduled_at,
                  **({'registeredAt':wait.created_at} if 'clockAt' in command else {})}
    elif operation == 'timer_signal':
        from agents.durable_responsibility import TIMER
        from .durable_runtime import MeetingResponsibilityRuntime
        runtime = MeetingResponsibilityRuntime(store=db, cron=None)
        item = runtime.existing(state['caseId'])
        occurrence = runtime.timer_store.delivery_event(timer_id=state['timerRef'])
        if 'clockAt' in command and datetime.fromisoformat(command['clockAt'].replace('Z','+00:00')) < datetime.fromisoformat(occurrence.scheduled_at.replace('Z','+00:00')):
            state_path.write_text(json.dumps(state,sort_keys=True))
            return {'accepted':False,'reason':'timer_not_due','observedAt':command['clockAt']}
        wake = runtime.responsibilities.accept_wake(responsibility_id=item.responsibility_id, kind=TIMER,
            source_ref=occurrence.timer_id, correlation_key=state['caseId'], dedupe_key=occurrence.dedupe_key,
            expected_checkpoint_version=item.checkpoint_version)
        if wake.accepted:
            runtime._record_wake(negotiation_id=state['caseId'], responsibility_id=item.responsibility_id,
                                 kind=TIMER, source_ref=occurrence.timer_id, wake_id=wake.wake_id)
        result = {'accepted': wake.accepted, 'wakeKind': TIMER, 'wakeSourceRef': occurrence.timer_id,
                  'responsibilityRef': item.responsibility_id, 'wakeRef': wake.wake_id,
                  **({'observedAt':next(event['created_at'] for event in reversed(runtime.responsibilities.events(item.responsibility_id)) if event['payload'].get('wake_id') == wake.wake_id)} if 'clockAt' in command else {})}
    elif operation == 'present_frontier':
        frontier = db.latest_decision_frontier(state['caseId'])
        db.record_negotiation_event(negotiation_id=state['caseId'], event_type='DECISION_FRONTIER_PRESENTED',
                                   actor_type='agent', actor_id='scheduling_agent', payload=frontier)
        current = db.get_negotiation(state['caseId'])
        db.transition_negotiation_state(state['caseId'], expected_state=current['status'], next_state='awaiting_requester_decision',
                                        patch={}, actor_id='system:decision_governor')
        result = {'boundary': 'REQUESTER_REQUIRED'}
    elif operation == 'requester_decision':
        result = apply_requester_decision({'negotiation_id': state['caseId'], 'action': 'requester_cancel',
                                          'requested_by_user_id': ctx.user_id}, store=db)
    else:
        raise ValueError('SIMULATION_TRANSPORT_ONLY')
    state_path.write_text(json.dumps(state, sort_keys=True))
    return result



@contextmanager
def _fixture_clock(clock_at):
    """Scope one injected scenario time to this fixture command; restore helpers."""
    from agents import durable_responsibility
    from . import store, gateway, durable_runtime
    instant = datetime.fromisoformat(clock_at.replace('Z','+00:00'))
    bindings = [(store,'utc_now_iso',lambda:clock_at),
                (durable_responsibility,'_now_iso',lambda:clock_at),
                (gateway,'_now_utc',lambda:instant),
                (durable_runtime,'_utc_now',lambda:instant)]
    originals = [(module,name,getattr(module,name)) for module,name,_ in bindings]
    try:
        for module,name,value in bindings:
            setattr(module,name,value)
        yield
    finally:
        for module,name,value in originals:
            setattr(module,name,value)


def _actor_time(state, command):
    if 'timeBasis' not in state:
        return None
    from contracts.state_evolution import EvolutionTimeBasisV1
    basis = EvolutionTimeBasisV1.model_validate(state['timeBasis'])
    instant = command.get('semanticTime')
    if basis.kind != 'domain' or basis.unit != 'second' or basis.epoch is None or isinstance(instant,bool) or not isinstance(instant,(int,float)) or not math.isfinite(instant) or not basis.start <= instant <= basis.stop or instant < state.get('semanticTime',basis.start):
        raise ValueError('INVALID_SCENARIO_CLOCK')
    state['semanticTime'] = instant
    from services.state_evolution_clock import meeting_time_iso
    return meeting_time_iso(basis,instant)

def actor_command(ctx, command):
    if not ctx or not ctx.authenticated:
        raise PermissionError('SIMULATION_GOVERNED_IDENTITY_REQUIRED')
    if command.get('workspaceRef', ctx.workspace_id) != ctx.workspace_id:
        raise PermissionError('SIMULATION_FOREIGN_WORKSPACE')
    if 'clockAt' in command:
        raise ValueError('SIMULATION_CLOCK_DERIVED_ONLY')
    root = ctx.hermes_home / 'simulation'
    root.mkdir(exist_ok=True)
    state_path = root / 'local-state.json'
    if command['operation'] == 'initialize':
        state = command['localState']
        state_path.write_text(json.dumps(state, sort_keys=True))
        profile = ctx.hermes_home / 'profiles' / state['profileRef']
        profile.mkdir(parents=True, exist_ok=True)
        (profile / 'profile.yaml').write_text('display_name: Simulated meeting participant\n')
        (profile / 'SOUL.md').write_text(command['instructions'])
        session = ctx.hermes_home / 'sessions' / state['sessionRef']
        session.mkdir(exist_ok=True)
        return {'userRef': ctx.user_id, 'workspaceRef': ctx.workspace_id, 'ownerRef': ctx.user_id,
                'profileRef': state['profileRef'], 'sessionRef': state['sessionRef'], 'role': state['role']}
    state = json.loads(state_path.read_text())
    clock_at = _actor_time(state,command)
    if state['role'] == 'requester':
        if clock_at is not None:
            with _fixture_clock(clock_at):
                return requester_command(ctx,state,{**command,'clockAt':clock_at},state_path)
        return requester_command(ctx, state, command, state_path)
    if command['operation'] != 'receive_feishu':
        raise ValueError('SIMULATION_TRANSPORT_ONLY')
    message = command['message']
    if message['toWorkspaceRef'] != ctx.workspace_id or message['toUserRef'] != ctx.user_id:
        raise PermissionError('SIMULATION_TRANSPORT_WRONG_RECIPIENT')
    subject = message['subjectRef']
    value = state['availability'][subject]
    if state['late'] and subject == 'alternative' and not message.get('timerReleased'):
        value = 'UNKNOWN'
    export = {'subjectRef': subject, 'availability': value}
    if subject == 'alternative' and value == 'AVAILABLE' and state['proposer']:
        export['proposal'] = state['slots'][subject]
    reply = {'fromUserRef': ctx.user_id, 'fromWorkspaceRef': ctx.workspace_id,
             'toUserRef': message['fromUserRef'], 'toWorkspaceRef': message['fromWorkspaceRef'],
             'messageRef': message['messageRef'] + ':reply', 'profileRef': state['profileRef'],
             'sessionRef': state['sessionRef'], 'facts': export}
    with (root / 'transport.jsonl').open('a') as stream:
        stream.write(json.dumps({'received': message, 'exported': reply}, sort_keys=True) + '\n')
    if clock_at is not None:
        state_path.write_text(json.dumps(state,sort_keys=True))
    return reply


def main():
    ctx = resolve_authenticated_tool_context()
    for line in sys.stdin:
        try:
            result = {'ok': True, 'result': actor_command(ctx, json.loads(line))}
        except (PermissionError, ValueError, KeyError) as exc:
            result = {'ok': False, 'error': str(exc)}
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
