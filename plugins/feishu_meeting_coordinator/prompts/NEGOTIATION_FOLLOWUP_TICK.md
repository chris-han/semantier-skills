Use this tool only in a no-agent follow-up cron tick context.
This tick must not create, repair, or re-enqueue any monitor job.
Do not claim cron ownership, call ensure/repair paths for cron maintenance, or enqueue retries.

Use exactly one follow-up cycle for negotiation {{negotiation_id}}.
Use context from workspace {{workspace_id}} and session {{session_id}}.

Do not infer requester intent, attendee slot preferences, or calendar state.
Use only explicit persisted state and governed assets.

Persist all state mutations before returning.
If the case is terminal (finished/finalization failed/cancelled), stop and do not continue.
If the case is terminal, perform cleanup only (including optional cron stop) and return.
If retry is not due, return wait state only.
Do not perform extra or repeated ticks in one call.
