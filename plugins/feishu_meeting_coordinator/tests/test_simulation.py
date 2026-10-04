import pytest

from feishu_meeting_coordinator.simulation import simulate_meeting


@pytest.mark.parametrize('count', [3, 4, 8, 12])
def test_parameter_sweep_records_production_planner_trace_deterministically(count, tmp_path):
    first = simulate_meeting(fixture_root=tmp_path, workspace_user_count=count, stable_seed='workshop-v1', workflow_version='2')
    second = simulate_meeting(fixture_root=tmp_path, workspace_user_count=count, stable_seed='workshop-v1', workflow_version='2')
    assert first == second
    assert len(first['participants']) == count
    assert first['steps'][-1]['boundary'] == 'REQUESTER_REQUIRED'
    assert len({p['participantRef'] for p in first['participants']}) == count
    assert len({p['workspaceRef'] for p in first['participants']}) == count
    assert len({p['userRef'] for p in first['participants']}) == count
    assert len({p['sessionRef'] for p in first['participants']}) == count
    assert first['participants'][0]['role'] == 'requester'
    assert any(s['eventType'] == 'FEISHU_TRANSPORT_DELIVERED' for s in first['steps'])
    assert all(s['simulationOnly'] for s in first['steps'])
    assert any(s['eventType'] == 'RESPONSIBILITY_WAKE_ACCEPTED' for s in first['steps']) == (count > 3)
    assert any(s['decision'] for s in first['steps'])
    assert first['semanticTraceHash'].startswith('sha256:')


def test_scenario_identity_pins_all_semantic_inputs_and_bounds_population(tmp_path):
    a = simulate_meeting(fixture_root=tmp_path, workspace_user_count=4, stable_seed='a', workflow_version='2')
    for inputs in ({'workspace_user_count': 8, 'stable_seed': 'a', 'workflow_version': '2'},
                   {'workspace_user_count': 4, 'stable_seed': 'b', 'workflow_version': '2'},
                   {'workspace_user_count': 4, 'stable_seed': 'a', 'workflow_version': '3'}):
        assert simulate_meeting(fixture_root=tmp_path, **inputs)['scenarioRef'] != a['scenarioRef']
    for count in (1, 2, 13, 2.5, True):
        with pytest.raises(ValueError):
            simulate_meeting(fixture_root=tmp_path, workspace_user_count=count, stable_seed='a', workflow_version='2')


@pytest.mark.parametrize('scenario', ['A', 'B', 'C', 'D', 'E', 'F'])
def test_six_semantic_scenarios(scenario, tmp_path):
    run = simulate_meeting(fixture_root=tmp_path, workspace_user_count=4, stable_seed='workshop-v1', workflow_version='2', scenario=scenario)
    frontier = next(s['decision'] for s in reversed(run['steps']) if s['decision'])
    if scenario in ('A', 'B', 'C', 'D', 'E'):
        assert {o['action'] for o in frontier['options']} == {'KEEP', 'MOVE'}
        keep = next(option for option in frontier['options'] if option['action'] == 'KEEP')
        assert keep['objectives']['attendance_coverage'] == .75
    if scenario == 'B':
        assert any(a['dominatedBy'] for a in frontier['excludedAlternatives'])
    if scenario == 'C':
        assert any(a['impact'] == 'MATERIAL' for s in run['steps'] if s['decision'] for a in s['decision']['informationActions'])
    if scenario == 'D':
        assert not any(s['agentAction'] == 'ASK' and s['actorRef'] == run['participants'][-1]['participantRef'] for s in run['steps'])
    if scenario == 'E':
        assert run['steps'][-1]['requesterChoice'] == 'CANCEL'
        assert run['steps'][-1]['effectState'] == 'SIMULATED_CANCELLED'
    if scenario == 'F':
        assert [o['action'] for o in frontier['options']] == ['CANCEL']
        assert not any(s['eventType'] == 'RESPONSIBILITY_WAIT_STARTED' for s in run['steps'])


def test_local_actor_exports_only_transport_facts_and_rejects_foreign_workspace(tmp_path):
    from dataclasses import replace
    from agents.auth_session import RequestContext
    from feishu_meeting_coordinator.simulation_actor import actor_command
    root = tmp_path / 'attendee'; root.mkdir(); (root / 'sessions').mkdir()
    ctx = RequestContext(authenticated=True, user_id='attendee', workspace_id='workspace-attendee',
                         workspace_slug='workspace-attendee', workspace_root=root, hermes_home=root)
    actor_command(ctx, {'operation': 'initialize', 'instructions': 'Fixture-owned behavior template',
        'localState': {'profileRef': 'local-profile', 'sessionRef': 'local-session', 'role': 'required_attendee',
                      'late': False, 'proposer': False, 'availability': {'original': 'AVAILABLE'},
                      'slots': {}, 'privateContext': 'never exported'}})
    message = {'toWorkspaceRef': ctx.workspace_id, 'toUserRef': ctx.user_id, 'fromWorkspaceRef': 'workspace-requester',
               'fromUserRef': 'requester', 'subjectRef': 'original', 'messageRef': 'message:1'}
    reply = actor_command(ctx, {'operation': 'receive_feishu', 'message': message})
    assert reply['facts'] == {'subjectRef': 'original', 'availability': 'AVAILABLE'}
    assert 'privateContext' not in str(reply)
    with pytest.raises(PermissionError, match='FOREIGN_WORKSPACE'):
        actor_command(ctx, {'operation': 'receive_feishu', 'workspaceRef': 'workspace-requester', 'message': message})
    with pytest.raises(ValueError, match='TRANSPORT_ONLY'):
        actor_command(ctx, {'operation': 'mutate_requester_negotiation'})
    with pytest.raises(PermissionError, match='WRONG_RECIPIENT'):
        actor_command(ctx, {'operation': 'receive_feishu', 'message': {**message, 'toWorkspaceRef': 'workspace-requester'}})
    with pytest.raises(PermissionError, match='GOVERNED_IDENTITY'):
        actor_command(replace(ctx, authenticated=False), {'operation': 'initialize'})
