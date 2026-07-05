Use this tool only in a no-agent follow-up cron tick context.

Use exactly one follow-up cycle for negotiation {{negotiation_id}}.
Use context from workspace {{workspace_id}} and session {{session_id}}.

Do not infer requester intent, attendee slot preferences, or calendar state.
Use only explicit persisted state and governed assets.

Persist all state mutations before returning.
If the case is terminal (finished/finalization failed/cancelled), stop and do not continue.
If retry is not due, return wait state only.
Do not perform extra or repeated ticks in one call.
