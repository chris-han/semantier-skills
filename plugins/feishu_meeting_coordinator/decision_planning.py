"""Bounded proposal formation. No requester authority or external effects live here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
from typing import Any, Literal

PLANNER_VERSION = 'meeting-decision-planner.v1'
UNKNOWN = 'UNKNOWN'


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('PLANNER_TIMEZONE_REQUIRED')
    return dt


@dataclass(frozen=True)
class MeetingBusinessAction:
    action_ref: str
    action: Literal['KEEP', 'MOVE', 'CANCEL']
    slot_id: str | None
    start_time: str | None = None
    end_time: str | None = None


@dataclass(frozen=True)
class MeetingInformationAction:
    action: Literal['ASK', 'WAIT', 'REFRESH', 'CLARIFY']
    target_ref: str
    slot_id: str | None
    expected_frontier_impact: Literal['MATERIAL', 'IMMATERIAL', 'UNKNOWN']
    estimated_coordination_cost: int
    basis: str


@dataclass(frozen=True)
class MeetingObjectiveVector:
    required_coverage: float | str
    attendance_coverage: float | str
    disruption_cost: float
    uncertainty: int
    coordination_cost: int
    preference: str = UNKNOWN
    fairness_cost: str = UNKNOWN
    urgency_fit: str = UNKNOWN


@dataclass(frozen=True)
class MeetingConstraintFinding:
    action_ref: str
    constraint: str
    status: str
    target_ref: str | None = None


@dataclass(frozen=True)
class MeetingDecisionOption:
    option_id: str
    action: str
    slot_id: str | None
    objective_vector: MeetingObjectiveVector
    binding_constraints: tuple[MeetingConstraintFinding, ...]
    tradeoff_summary: str
    dominance_status: str = 'NON_DOMINATED'


@dataclass(frozen=True)
class MeetingDecisionPlanningBasis:
    negotiation_id: str
    event_revision_id: str
    original_slot: dict[str, Any]
    participants: tuple[dict[str, Any], ...]
    candidate_slots: tuple[dict[str, Any], ...] = ()
    availability: tuple[dict[str, Any], ...] = ()
    followup_counts: tuple[tuple[str, int], ...] = ()
    max_followups: int = 3
    meeting_necessity: str = UNKNOWN
    basis_refs: tuple[str, ...] = ()
    revision_current: bool | None = True
    identity_bound: bool | None = True


@dataclass(frozen=True)
class MeetingDecisionFrontier:
    negotiation_id: str
    event_revision_id: str
    input_hash: str
    capability_frontier: tuple[str, ...]
    pareto_frontier: tuple[str, ...]
    decision_frontier: tuple[MeetingDecisionOption, ...]
    binding_constraints: tuple[MeetingConstraintFinding, ...]
    excluded_alternatives: tuple[dict[str, Any], ...]
    information_actions: tuple[MeetingInformationAction, ...]
    sufficient_progress_disposition: str
    basis_refs: tuple[str, ...]
    planner_version: str = PLANNER_VERSION
    schema_version: str = 'meeting_decision_frontier.v1'

    def to_dict(self) -> dict[str, Any]:
        # JSON values are the transport contract, with no wall-clock nondeterminism.
        result = json.loads(canonical_json(asdict(self)))
        result['output_hash'] = hashlib.sha256(canonical_json(result).encode()).hexdigest()
        return result


def _participants(basis):
    return sorted((p for p in basis.participants if p.get('role') != 'requester'),
                  key=lambda p: p['attendee_user_id'])


def _availability(basis, action, participant):
    rows = [r['status'] for r in basis.availability
            if r['slot_id'] == action.slot_id and r['attendee_user_id'] == participant['attendee_user_id']]
    if not rows:
        return UNKNOWN
    if len(set(rows)) != 1:
        raise ValueError('PLANNER_CONFLICTING_AVAILABILITY')
    if rows[0] not in ('AVAILABLE', 'UNAVAILABLE', UNKNOWN, 'NOT_APPLICABLE'):
        raise ValueError('PLANNER_INVALID_AVAILABILITY')
    return rows[0]


def build_business_actions(basis):
    if len(basis.candidate_slots) > 64 or len(basis.participants) > 128:
        raise ValueError('PLANNER_ENUMERATION_BOUND_EXCEEDED')
    actions = []
    original = basis.original_slot
    actions.append(MeetingBusinessAction('KEEP:original', 'KEEP', original['slot_id'],
                                         original['start_time'], original['end_time']))
    seen = {original['slot_id']}
    for s in sorted(basis.candidate_slots, key=lambda s: s['slot_id']):
        if s['slot_id'] in seen:
            raise ValueError('PLANNER_DUPLICATE_SLOT')
        seen.add(s['slot_id'])
        actions.append(MeetingBusinessAction('MOVE:' + s['slot_id'], 'MOVE', s['slot_id'],
                                             s['start_time'], s['end_time']))
    if basis.meeting_necessity in ('RESOLVED_ASYNCHRONOUSLY', 'REQUESTER_NOT_NECESSARY', 'PURPOSE_EXPIRED', 'POLICY_CANCEL'):
        actions.append(MeetingBusinessAction('CANCEL', 'CANCEL', None))
    return tuple(actions)


def evaluate_hard_constraints(basis, action):
    findings = []
    for name, value in (('event_revision_current', basis.revision_current), ('participant_identity_bound', basis.identity_bound)):
        if value is not True:
            findings.append(MeetingConstraintFinding(action.action_ref, name, UNKNOWN if value is None else 'UNAVAILABLE'))
    if action.action != 'CANCEL':
        duration = _time(action.end_time) - _time(action.start_time)
        if duration.total_seconds() <= 0 or duration != _time(basis.original_slot['end_time']) - _time(basis.original_slot['start_time']):
            findings.append(MeetingConstraintFinding(action.action_ref, 'duration_compatible', 'UNAVAILABLE'))
        for p in _participants(basis):
            status = _availability(basis, action, p)
            if p.get('required_for_consent') and status != 'AVAILABLE':
                findings.append(MeetingConstraintFinding(action.action_ref, 'required_participation', status, p['attendee_user_id']))
    return tuple(findings)


def compute_objective_vector(basis, action):
    participants = sorted(basis.participants, key=lambda person: person['attendee_user_id'])
    required = [p for p in _participants(basis) if p.get('required_for_consent')]
    if action.action == 'CANCEL':
        return MeetingObjectiveVector('NOT_APPLICABLE', 'NOT_APPLICABLE', 0, 0, sum(c for _, c in basis.followup_counts))
    states = [_availability(basis, action, p) for p in participants]
    coverage = lambda ps: sum(_availability(basis, action, p) == 'AVAILABLE' for p in ps) / len(ps) if ps else 'NOT_APPLICABLE'
    disruption = 0.0 if action.action == 'KEEP' else 1 + abs((_time(action.start_time) - _time(basis.original_slot['start_time'])).total_seconds()) / 86400
    return MeetingObjectiveVector(coverage(required), coverage(participants), disruption,
                                  states.count(UNKNOWN), sum(c for _, c in basis.followup_counts))


def _dominates(a, b):
    # Cancellation lives in a different purpose tier, never a numeric attendance score.
    if a.action == 'CANCEL' or b.action == 'CANCEL':
        return False
    av, bv = a.objective_vector, b.objective_vector
    pairs = [(av.required_coverage, bv.required_coverage), (av.attendance_coverage, bv.attendance_coverage),
             (-av.disruption_cost, -bv.disruption_cost), (-av.uncertainty, -bv.uncertainty),
             (-av.coordination_cost, -bv.coordination_cost)]
    comparable = [(x, y) for x, y in pairs if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    return all(x >= y for x, y in comparable) and any(x > y for x, y in comparable)


def pareto_frontier(options):
    return tuple(o for o in options if not any(_dominates(other, o) for other in options))


def apply_hierarchical_policy(basis, options):
    cancellations = tuple(o for o in options if o.action == 'CANCEL')
    if cancellations:
        return cancellations
    # Preserve materially distinct attendance/preservation tradeoffs, deduplicate equivalent vectors.
    seen = set()
    result = []
    for option in sorted(options, key=lambda o: (o.action != 'KEEP', o.objective_vector.disruption_cost, o.option_id)):
        signature = canonical_json(asdict(option.objective_vector))
        if signature not in seen:
            seen.add(signature)
            result.append(option)
    return tuple(result)


def _frontiers(basis):
    actions = build_business_actions(basis)
    findings, feasible = [], []
    for action in actions:
        blocked = evaluate_hard_constraints(basis, action)
        findings.extend(blocked)
        if not blocked:
            vector = compute_objective_vector(basis, action)
            summary = ('Meeting purpose explicitly no longer requires synchronous attendance' if action.action == 'CANCEL'
                       else f'{action.action} {action.start_time}; required coverage {vector.required_coverage}; known attendance {vector.attendance_coverage}; disruption {vector.disruption_cost:g}; unknown {vector.uncertainty}')
            feasible.append(MeetingDecisionOption(action.action_ref, action.action, action.slot_id, vector, (), summary))
    pareto = pareto_frontier(feasible)
    decision = apply_hierarchical_policy(basis, pareto)
    return actions, tuple(findings), tuple(feasible), pareto, decision


def evaluate_information_actions(basis):
    actions, _, _, _, decision = _frontiers(basis)
    current = tuple(o.option_id for o in decision)
    counts = dict(basis.followup_counts)
    information = []
    for p in _participants(basis):
        for action in actions:
            if action.action == 'CANCEL' or _availability(basis, action, p) != UNKNOWN:
                continue
            material = False
            for status in ('AVAILABLE', 'UNAVAILABLE'):
                response = {'slot_id': action.slot_id, 'attendee_user_id': p['attendee_user_id'], 'status': status}
                alternate = replace(basis, availability=tuple(r for r in basis.availability
                    if (r['slot_id'], r['attendee_user_id']) != (action.slot_id, p['attendee_user_id'])) + (response,))
                _, _, _, _, changed = _frontiers(alternate)
                if tuple(o.option_id for o in changed) != current:
                    material = True
            # Required UNKNOWN can jointly block feasibility even if one reply alone cannot close it.
            if p.get('required_for_consent'):
                unknown_required = {other['attendee_user_id'] for other in _participants(basis)
                    if other.get('required_for_consent') and _availability(basis, action, other) == UNKNOWN}
                joint = replace(basis, availability=tuple(r for r in basis.availability
                    if not (r['slot_id'] == action.slot_id and r['attendee_user_id'] in unknown_required)) + tuple(
                    {'slot_id': action.slot_id, 'attendee_user_id': target, 'status': 'AVAILABLE'}
                    for target in sorted(unknown_required)))
                _, _, _, _, changed = _frontiers(joint)
                material = material or tuple(o.option_id for o in changed) != current
            impact = 'MATERIAL' if material else 'IMMATERIAL'
            remaining = counts.get(p['attendee_user_id'], 0) < basis.max_followups
            information.append(MeetingInformationAction('ASK' if material and remaining else 'WAIT',
                p['attendee_user_id'], action.slot_id, impact, 1 if material and remaining else 0,
                'reply_can_change_frontier' if material else 'reply_cannot_change_frontier'))
    return tuple(information)


def form_decision_frontier(basis):
    actions, findings, feasible, pareto, decision = _frontiers(basis)
    info = evaluate_information_actions(basis)
    raw = asdict(basis)
    for key in ('participants', 'candidate_slots', 'availability'):
        raw[key] = sorted(raw[key], key=canonical_json)
    raw['followup_counts'] = sorted(raw['followup_counts'])
    raw['basis_refs'] = sorted(set(raw['basis_refs']))
    raw['planner_version'] = PLANNER_VERSION
    input_hash = hashlib.sha256(canonical_json(raw).encode()).hexdigest()
    excluded = []
    for action in actions:
        if action.action_ref not in {o.option_id for o in decision}:
            blocked = [asdict(c) for c in findings if c.action_ref == action.action_ref]
            option = next((o for o in feasible if o.option_id == action.action_ref), None)
            excluded.append({'action_ref': action.action_ref, 'binding_constraints': blocked,
                             'dominated_by': [o.option_id for o in feasible if option and _dominates(o, option)],
                             'reason': 'HARD_CONSTRAINT' if blocked else 'DOMINATED' if option not in pareto else 'HIERARCHICAL_POLICY'})
    return MeetingDecisionFrontier(basis.negotiation_id, basis.event_revision_id, input_hash,
        tuple(o.option_id for o in feasible), tuple(o.option_id for o in pareto), decision, findings,
        tuple(excluded), info, 'CONTINUE_INFORMATION' if any(a.action == 'ASK' for a in info)
        else 'PRESENT_FRONTIER' if decision else 'WAIT_AUTHORITY', tuple(sorted(set(basis.basis_refs))))


def project_decision_frontier(frontier):
    value = frontier.to_dict()
    return {
        'plannerVersion': frontier.planner_version,
        'inputHash': 'sha256:' + frontier.input_hash,
        'outputHash': 'sha256:' + value['output_hash'],
        'capabilityFrontier': value['capability_frontier'],
        'paretoFrontier': value['pareto_frontier'],
        'decisionFrontier': [o['option_id'] for o in value['decision_frontier']],
        'options': [{'optionRef': o['option_id'], 'action': o['action'], 'targetRef': o['slot_id'],
                     'objectives': o['objective_vector'], 'summary': o['tradeoff_summary']}
                    for o in value['decision_frontier']],
        'bindingConstraints': value['binding_constraints'],
        'excludedAlternatives': [{'alternativeRef': a['action_ref'], 'reason': a['reason'],
                                 'dominatedBy': a['dominated_by'], 'constraints': a['binding_constraints']}
                                for a in value['excluded_alternatives']],
        'informationActions': [{'action': a['action'], 'targetRef': a['target_ref'],
                                'subjectRef': a['slot_id'], 'impact': a['expected_frontier_impact'],
                                'cost': a['estimated_coordination_cost'], 'basis': a['basis']}
                               for a in value['information_actions']],
        'disposition': value['sufficient_progress_disposition'], 'basisRefs': value['basis_refs'],
    }
