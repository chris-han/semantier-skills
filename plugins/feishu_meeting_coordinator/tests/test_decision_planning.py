from dataclasses import replace

from feishu_meeting_coordinator.decision_planning import (
    MeetingDecisionPlanningBasis, form_decision_frontier,
)


def basis():
    return MeetingDecisionPlanningBasis(
        negotiation_id='n1', event_revision_id='r1',
        original_slot={'slot_id': 'original', 'start_time': '2026-10-05T10:00:00Z',
                       'end_time': '2026-10-05T10:30:00Z'},
        participants=tuple({'attendee_user_id': p, 'required_for_consent': p in ('alice', 'bob')}
                           for p in ('alice', 'bob', 'carol', 'dan')),
        candidate_slots=tuple({'slot_id': s, 'start_time': t, 'end_time': e}
                              for s, t, e in (
                                  ('move', '2026-10-05T15:00:00Z', '2026-10-05T15:30:00Z'),
                                  ('blocked', '2026-10-05T11:00:00Z', '2026-10-05T11:30:00Z'))),
        availability=tuple({'attendee_user_id': p, 'slot_id': s, 'status':
                            'UNAVAILABLE' if (s, p) in (('original', 'carol'), ('blocked', 'bob')) else 'AVAILABLE'}
                           for s in ('original', 'move', 'blocked')
                           for p in ('alice', 'bob', 'carol', 'dan')),
    )


def test_preserves_keep_move_tradeoff_and_explains_hard_exclusion():
    f = form_decision_frontier(basis()).to_dict()
    assert {o['action'] for o in f['decision_frontier']} == {'KEEP', 'MOVE'}
    assert 'MOVE:blocked' not in f['capability_frontier']
    assert any(c['action_ref'] == 'MOVE:blocked' and c['status'] == 'UNAVAILABLE'
               for c in f['binding_constraints'])
    assert all(o['objective_vector']['fairness_cost'] == 'UNKNOWN' for o in f['decision_frontier'])


def test_input_order_invariant_and_pinned_semantic_hash():
    b = basis()
    other = replace(b, participants=b.participants[::-1], candidate_slots=b.candidate_slots[::-1],
                    availability=b.availability[::-1])
    assert form_decision_frontier(b).to_dict() == form_decision_frontier(other).to_dict()
    assert form_decision_frontier(replace(b, event_revision_id='r2')).input_hash != form_decision_frontier(b).input_hash


def test_required_unknown_requests_material_information_without_guessing():
    b = basis()
    b = replace(b, availability=tuple(a for a in b.availability
                                     if (a['slot_id'], a['attendee_user_id']) != ('move', 'bob')))
    f = form_decision_frontier(b).to_dict()
    assert 'MOVE:move' not in f['capability_frontier']
    assert any(a['target_ref'] == 'bob' and a['expected_frontier_impact'] == 'MATERIAL'
               for a in f['information_actions'])
    assert any(c['status'] == 'UNKNOWN' for c in f['binding_constraints'])


def test_cancel_requires_explicit_necessity_evidence():
    assert not any(o['action'] == 'CANCEL' for o in form_decision_frontier(basis()).to_dict()['decision_frontier'])
    f = form_decision_frontier(replace(basis(), meeting_necessity='RESOLVED_ASYNCHRONOUSLY')).to_dict()
    assert [o['action'] for o in f['decision_frontier']] == ['CANCEL']


def test_total_attendance_counts_explicit_requester_availability():
    b = basis()
    people = b.participants[:3] + ({'attendee_user_id': 'organizer', 'role': 'requester', 'required_for_consent': False},)
    availability = tuple(row for row in b.availability if row['attendee_user_id'] != 'dan') + tuple(
        {'attendee_user_id': 'organizer', 'slot_id': slot, 'status': 'AVAILABLE'}
        for slot in ('original', 'move', 'blocked'))
    frontier = form_decision_frontier(replace(b, participants=people, availability=availability)).to_dict()
    keep = next(option for option in frontier['decision_frontier'] if option['action'] == 'KEEP')
    move = next(option for option in frontier['decision_frontier'] if option['action'] == 'MOVE')
    assert keep['objective_vector']['attendance_coverage'] == .75
    assert move['objective_vector']['attendance_coverage'] == 1


def test_required_unknown_is_immaterial_when_even_joint_reply_cannot_change_frontier():
    b = basis()
    # Full original attendance dominates every move regardless of the missing reply.
    rows = tuple({**row, 'status': 'AVAILABLE'} if row['slot_id'] == 'original' else row
                 for row in b.availability if (row['slot_id'], row['attendee_user_id']) != ('move', 'bob'))
    f = form_decision_frontier(replace(b, availability=rows)).to_dict()
    assert [o['action'] for o in f['decision_frontier']] == ['KEEP']
    assert not any(a['action'] == 'ASK' for a in f['information_actions'])
    cancelled = form_decision_frontier(replace(b, availability=rows, meeting_necessity='RESOLVED_ASYNCHRONOUSLY')).to_dict()
    assert not any(a['action'] == 'ASK' for a in cancelled['information_actions'])


def test_dominated_move_is_excluded_and_information_budget_is_bounded():
    b = basis()
    inferior = {'slot_id': 'inferior', 'start_time': '2026-10-06T15:00:00Z', 'end_time': '2026-10-06T15:30:00Z'}
    b = replace(b, candidate_slots=b.candidate_slots + (inferior,), availability=b.availability + tuple(
        {'slot_id': 'inferior', 'attendee_user_id': p, 'status': 'AVAILABLE' if p != 'carol' else 'UNAVAILABLE'}
        for p in ('alice', 'bob', 'carol', 'dan')))
    f = form_decision_frontier(b).to_dict()
    assert 'MOVE:inferior' in f['capability_frontier']
    assert 'MOVE:inferior' not in f['pareto_frontier']
    assert any(o['action_ref'] == 'MOVE:inferior' and o['dominated_by'] for o in f['excluded_alternatives'])
    missing = replace(b, availability=(), followup_counts=(('alice', 3), ('bob', 3)), max_followups=3)
    assert not any(a['action'] == 'ASK' and a['target_ref'] in ('alice', 'bob')
                   for a in form_decision_frontier(missing).to_dict()['information_actions'])
