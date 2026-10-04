"""Disposable multi-workspace fixtures driving the production domain store/planner.

Fixture authority is isolated from the live auth DB. Each attendee executes in a
separate process with its own governed context and workspace-local files. The
requester learns only facts exported in the recorded Feishu transport. Replay
never calls this module. No external Feishu/calendar client is instantiated.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml
from .decision_planning import PLANNER_VERSION, canonical_json


def _hash(value):
    return 'sha256:' + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def simulate_meeting(*, workspace_user_count=4, stable_seed='workshop-v1', workflow_version='2', scenario='A',
                     context=None, fixture_root=None):
    if type(workspace_user_count) is not int or not 3 <= workspace_user_count <= 12:
        raise ValueError('workspace_user_count must be an integer from 3 to 12')
    if scenario not in tuple('ABCDEF') or not isinstance(stable_seed, str) or not 1 <= len(stable_seed) <= 128:
        raise ValueError('invalid simulation scenario or seed')
    if not isinstance(workflow_version, str) or not 1 <= len(workflow_version) <= 32:
        raise ValueError('invalid workflow version')
    if context is not None:
        if not context.authenticated:
            raise PermissionError('SIMULATION_AUTHENTICATION_REQUIRED')
        parent = (context.workspace_root.resolve() / 'runs' / 'meeting-simulation')
    elif fixture_root is not None:
        parent = Path(fixture_root).resolve()
    else:
        raise ValueError('SIMULATION_GOVERNED_ROOT_REQUIRED')
    parent.mkdir(parents=True, exist_ok=True)
    request = {'workspace_user_count': workspace_user_count, 'stable_seed': stable_seed,
               'workflow_version': workflow_version, 'scenario': scenario}
    with tempfile.TemporaryDirectory(prefix='run-', dir=parent) as directory:
        root = Path(directory)
        env = {**os.environ, 'SEMANTIER_AUTH_DB_PATH': str(root / 'auth.sqlite'),
               'SEMANTIER_LOCAL_STATE_DIR': str(root / 'platform'),
               'PYTHONPATH': os.pathsep.join(str(p) for p in sys.path if p)}
        for key in ('HERMES_SESSION_USER_ID', 'HERMES_SESSION_WORKSPACE_OWNER_ID', 'SEMANTIER_USER_ID', 'SEMANTIER_WORKSPACE_ID'):
            env.pop(key, None)
        result = subprocess.run([sys.executable, '-m', 'feishu_meeting_coordinator.simulation'],
                                input=canonical_json(request), text=True, capture_output=True, env=env, timeout=90)
        if result.returncode:
            raise ValueError('SIMULATION_FIXTURE_FAILED: ' + result.stderr[-1000:])
        return json.loads(result.stdout)


def _run(request):
    from agents.auth_db import ensure_auth_db, save_users, save_organizations
    from agents.meeting_demo_users import seed_meeting_demo_users
    from agents.gateway_identity import ensure_workspace_paths
    seeds = {name: yaml.safe_load((Path(__file__).with_name('simulation_profiles') / f'{name}.yaml').read_text())
             for name in ('requester', 'cooperative', 'conflict')}
    count = request['workspace_user_count']; scenario = request['scenario']
    identity = {'workspaceUserCount': count, 'stableSeed': request['stable_seed'],
                'workflowVersion': request['workflow_version'], 'plannerVersion': PLANNER_VERSION,
                'scenario': scenario, 'profileSeedsHash': _hash(seeds), 'generatorVersion': 'meeting-workspace-scenario.v2'}
    scenario_ref = 'meeting-scenario:' + _hash(identity).split(':')[1]
    suffix = _hash(identity).split(':')[1][:16]
    org = 'simulation-org-' + suffix
    participants = []
    users = {}
    seeded = seed_meeting_demo_users(local_demo=True)[:count]
    for i, user in enumerate(seeded):
        ref = user['user_id']; ws = user['workspace_id']
        role = 'requester' if i == 0 else 'required_attendee' if i <= 2 else 'optional_attendee'
        seed = seeds['requester' if i == 0 else 'cooperative' if i % 2 else 'conflict']
        session = f'sim-session-{suffix}-{i:02d}'
        participants.append({'participantRef': ref, 'userRef': ref, 'workspaceRef': ws, 'ownerRef': ref,
                             'label': user['display_name'], 'login': user['password_login_name'], 'avatarUrl': user['avatar_url'], 'role': role,
                             'required': 0 < i <= 2, 'profileRef': seed['profile_id'], 'sessionRef': session})
        users[ref] = {**user, 'organization_id': org, 'organization_name': org,
                     'membership_status': 'active', 'member_role': 'owner',
                     'organization_memberships': [{'organization_id': org, 'organization_name': org,
                         'membership_status': 'active', 'member_role': 'owner'}]}
    save_organizations({org: {'organization_id': org, 'display_name': org, 'dataset_type': 'REAL',
                             'allow_self_join': False, 'created_by': participants[0]['userRef'], 'created_at': '2026-10-05T00:00:00Z'}})
    save_users(users)
    original = {'start_time': '2026-10-05T02:00:00Z', 'end_time': '2026-10-05T02:30:00Z', 'timezone': 'UTC'}
    slots = {'original': original, 'alternative': {'start_time': '2026-10-05T07:00:00Z', 'end_time': '2026-10-05T07:30:00Z', 'timezone': 'UTC'},
             'blocked': {'start_time': '2026-10-05T03:00:00Z', 'end_time': '2026-10-05T03:30:00Z', 'timezone': 'UTC'},
             'dominated': {'start_time': '2026-10-06T07:00:00Z', 'end_time': '2026-10-06T07:30:00Z', 'timezone': 'UTC'}}
    actors = {}; roots = []
    def command(actor, payload):
        actor.stdin.write(canonical_json(payload) + '\n'); actor.stdin.flush()
        result = json.loads(actor.stdout.readline())
        if not result['ok']: raise PermissionError(result['error'])
        return result['result']
    try:
        for i, p in enumerate(participants):
            root, _ = ensure_workspace_paths(p['workspaceRef']); roots.append(root)
            env = {**os.environ, 'SEMANTIER_USER_ID': p['userRef'], 'SEMANTIER_WORKSPACE_ID': p['workspaceRef']}
            actor = subprocess.Popen([sys.executable, '-m', 'feishu_meeting_coordinator.simulation_actor'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            actors[p['userRef']] = actor
            availability = {subject: 'AVAILABLE' for subject in slots}
            if i >= 3: availability['original'] = 'UNAVAILABLE'
            if i == 1: availability['blocked'] = 'UNAVAILABLE'
            if scenario == 'D' and i == count - 1 and i >= 3: availability['blocked'] = 'UNKNOWN'
            seed = seeds['requester' if i == 0 else 'cooperative' if i % 2 else 'conflict']
            bound = command(actor, {'operation': 'initialize', 'localState': {
                'availability': availability, 'slots': slots, 'late': i == 2, 'proposer': i == 2,
                'profileRef': p['profileRef'], 'sessionRef': p['sessionRef'], 'role': p['role']}, 'instructions': seed['instructions']})
            if any(bound[key] != p[key] for key in ('userRef', 'workspaceRef', 'ownerRef', 'sessionRef')):
                raise ValueError('SIMULATION_BINDING_MISMATCH')
        requester = participants[0]
        requester_actor = actors[requester['userRef']]
        command(requester_actor, {'operation': 'initialize_negotiation', 'participants': participants,
                                  'scenarioRef': scenario_ref, 'scenario': scenario})
        states = {p['userRef']: 'READY' for p in participants}; steps = []; frontier = None; known = []; slot_ids = {}
        def record(event_type, node, actor=None, action=None, boundary=None, **detail):
            index = len(steps)
            step = {'step': index, 'eventId': f'{scenario_ref}:event:{index:03d}', 'eventType': event_type,
                'occurredAt': (datetime(2026, 10, 5, tzinfo=timezone.utc) + timedelta(seconds=index)).isoformat().replace('+00:00', 'Z'),
                'nodeRef': node, 'actorRef': actor, 'agentAction': action, 'boundary': boundary,
                'decision': frontier,
                'participants': [{'participantRef': p['participantRef'], 'state': states[p['userRef']]} for p in participants],
                'knownEvidence': list(known), 'simulationOnly': True, **detail}
            steps.append(step)
        def transport(p, subject, released=False):
            message = {'fromUserRef': requester['userRef'], 'fromWorkspaceRef': requester['workspaceRef'],
                       'toUserRef': p['userRef'], 'toWorkspaceRef': p['workspaceRef'], 'subjectRef': subject,
                       'messageRef': f'{scenario_ref}:message:{len(steps):03d}', 'timerReleased': released}
            record('FEISHU_TRANSPORT_SENT', 'collect_candidate_slots', actor=requester['userRef'], action='ASK', transport=message)
            reply = command(actors[p['userRef']], {'operation': 'receive_feishu', 'message': message})
            record('FEISHU_TRANSPORT_EXPORTED', 'collect_votes', actor=p['userRef'], action='REPLY', transport=reply,
                   localFacts=reply['facts'])
            admitted = command(requester_actor, {'operation': 'receive_feishu', 'message': reply})
            known[:] = admitted['knownEvidence']
            states[p['userRef']] = 'WAITING_TIMER' if reply['facts']['availability'] == 'UNKNOWN' else 'REPLIED'
            record('FEISHU_TRANSPORT_DELIVERED', 'collect_votes', actor=requester['userRef'], transport=reply)
            return reply
        record('SIMULATION_STARTED', 'observe_meeting_event')
        for p in participants[1:]:
            reply = transport(p, 'original')
        for subject in ('alternative', 'blocked', 'dominated'):
            for p in participants[1:]:
                if scenario == 'D' and subject == 'blocked' and p is participants[-1]: continue
                transport(p, subject)
        def compute():
            nonlocal frontier
            observation = command(requester_actor, {'operation': 'planner_tick'})
            frontier = observation['decision']
            slot_ids.update({subject: slot_id for slot_id, subject in observation['slotSubjects'].items()})
            record('DECISION_FRONTIER_COMPUTED', 'form_decision_frontier', actor=requester['userRef'], sourceEventRef=observation['sourceEventRef'])
        compute()
        asks = [a for a in frontier['informationActions'] if a['action'] == 'ASK']
        if asks:
            wait = command(requester_actor, {'operation': 'prepare_wait'})
            record('RESPONSIBILITY_WAIT_STARTED', 'wait_followup', waitRef=wait['waitRef'], resumeConditionRef='material_participant_reply_or_timer')
            wake = command(requester_actor, {'operation': 'timer_signal'})
            if not wake['accepted']: raise ValueError('SIMULATION_TIMER_WAKE_REJECTED')
            record('RESPONSIBILITY_WAKE_ACCEPTED', 'wait_followup', actor=requester['userRef'], wakeKind=wake['wakeKind'],
                   wakeSourceRef=wake['wakeSourceRef'], responsibilityRef=wake['responsibilityRef'])
            for info in asks:
                subject = next(subject for subject, slot_id in slot_ids.items() if slot_id == info['subjectRef'])
                p = next(p for p in participants if p['userRef'] == info['targetRef'])
                record('INFORMATION_ACTION_SELECTED', 'evaluate_information_value', actor=requester['userRef'], action='ASK', subjectRef=subject)
                reply = transport(p, subject, True)
                compute()
        record('DECISION_FRONTIER_PRESENTED', 'requester_decision', actor=requester['userRef'], boundary='REQUESTER_REQUIRED')
        command(requester_actor, {'operation': 'present_frontier'})
        if scenario == 'E':
            command(requester_actor, {'operation': 'requester_decision'})
            record('REQUESTER_DECISION_RECORDED', 'requester_decision', actor=requester['userRef'], requesterChoice='CANCEL')
            record('SIMULATED_EFFECT_COMPLETED', 'cancel_meeting', actor=requester['userRef'], boundary='TERMINAL', requesterChoice='CANCEL', effectState='SIMULATED_CANCELLED')
        result = {'schemaVersion': 'workflow_simulation_trace.v1', 'scenarioRef': scenario_ref, 'identity': identity,
                  'participants': participants, 'requesterProfileRef': seeds['requester']['profile_id'], 'steps': steps}
        result['semanticTraceHash'] = _hash(result)
        return result
    finally:
        for actor in actors.values():
            actor.stdin.close()
            try: actor.wait(timeout=5)
            except subprocess.TimeoutExpired: actor.kill(); actor.wait()
            actor.stdout.close(); actor.stderr.close()


if __name__ == '__main__':
    print(canonical_json(_run(json.load(sys.stdin))))
