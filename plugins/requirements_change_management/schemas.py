SCHEMAS = {
    "requirements_change_compare": {"type":"object","properties":{"requirement_id":{"type":"string"},"before":{"type":"string"},"after":{"type":"string"}},"required":["requirement_id","before","after"]},
    "requirements_change_impact": {"type":"object","properties":{"requirement_id":{"type":"string"},"obligations":{"type":"array"}},"required":["requirement_id","obligations"]},
    "requirements_change_baseline": {"type":"object","properties":{}},
    "requirements_change_propose": {"type":"object","properties":{"kind":{"type":"string"},"payload":{"type":"object"}},"required":["kind","payload"]},
    "requirements_change_submit_review": {"type":"object","properties":{"candidate_ref":{"type":"string"},"reviewer_ref":{"type":"string"},"disposition":{"type":"string"},"basis_refs":{"type":"array"},"idempotency_key":{"type":"string"}},"required":["candidate_ref","reviewer_ref","disposition","basis_refs","idempotency_key"]},
    "requirements_change_publish": {"type":"object","properties":{"candidate_ref":{"type":"string"},"review_receipt_ref":{"type":"string"},"expected_head_ref":{"type":"string"},"idempotency_key":{"type":"string"}},"required":["candidate_ref","review_receipt_ref","expected_head_ref","idempotency_key"]},
}
