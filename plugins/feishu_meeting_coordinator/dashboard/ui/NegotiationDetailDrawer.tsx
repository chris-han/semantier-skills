export type NegotiationDetailDrawerProps = {
  taskId: string;
  extensionId: string;
  negotiationId?: string;
  metadata: Record<string, unknown>;
  onAction: (actionId: string, payload?: Record<string, unknown>) => void;
  onClose: () => void;
};

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function safeCount(value: unknown, fallback = 0): number {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

export default function NegotiationDetailDrawer({
  negotiationId,
  metadata,
  onAction,
  onClose,
}: NegotiationDetailDrawerProps) {
  const title = text(metadata.meeting_title, "Meeting negotiation");
  const status = text(metadata.status, "pending");
  const followupStatus = text(metadata.followup_cron_status, "not_created");
  const followupCronJobId = text(metadata.followup_cron_job_id);
  const nextFollowupAt = text(metadata.next_followup_at, "not scheduled");
  const lastTickAt = text(metadata.followup_cron_last_tick_at, "never");
  const failureCount = safeCount(metadata.followup_cron_failure_count, 0);
  const terminalAuthority = text(metadata.terminal_authority);
  const terminalAt = text(metadata.terminal_at);
  const terminalReason = text(metadata.terminal_reason);
  const terminalEventRevisionId = text(metadata.terminal_event_revision_id);
  const declinedAttendee = text(metadata.declined_attendee_name, "Declined attendee");
  const bestSlot = text(metadata.best_slot, "No candidate slot");
  const bestSlotId = text(metadata.best_slot_id);
  const missingAttendees = asStringArray(metadata.missing_required_attendee_names);
  const showRequesterActions = status === "awaiting_requester_decision";

  return (
    <section
      className="feishu-meeting-negotiation-detail"
      data-negotiation-id={negotiationId}
    >
      <header>
        <h2>{title}</h2>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>
      <dl>
        <dt>Status</dt>
        <dd>{status}</dd>
        <dt>Negotiation</dt>
        <dd>{negotiationId || "unassigned"}</dd>
        <dt>Declined attendee</dt>
        <dd>{declinedAttendee}</dd>
        <dt>Follow-up cron</dt>
        <dd>{followupStatus}</dd>
        <dt>Follow-up cron job</dt>
        <dd>{followupCronJobId || "not assigned"}</dd>
        <dt>Next follow-up</dt>
        <dd>{nextFollowupAt}</dd>
        <dt>Last cron tick</dt>
        <dd>{lastTickAt}</dd>
        <dt>Cron failures</dt>
        <dd>{failureCount}</dd>
        <dt>Terminal authority</dt>
        <dd>{terminalAuthority || "n/a"}</dd>
        <dt>Terminal time</dt>
        <dd>{terminalAt || "n/a"}</dd>
        <dt>Terminal reason</dt>
        <dd>{terminalReason || "n/a"}</dd>
        <dt>Terminal revision</dt>
        <dd>{terminalEventRevisionId || "n/a"}</dd>
        <dt>Best slot</dt>
        <dd>{bestSlot}</dd>
        <dt>Missing required attendees</dt>
        <dd>
          {missingAttendees.length > 0 ? missingAttendees.join(", ") : "none"}
        </dd>
      </dl>
      <footer>
        <button type="button" onClick={() => onAction("nudge_unblock")}>
          Nudge
        </button>
        <button type="button" onClick={() => onAction("finalize")}>
          Finalize
        </button>
        {showRequesterActions ? (
          <>
            <button
              type="button"
              onClick={() =>
                onAction("requester_decision", { action: "requester_keep_original" })
              }
            >
              Keep original
            </button>
            {bestSlotId ? (
              <button
                type="button"
                onClick={() =>
                  onAction("requester_decision", {
                    action: "requester_select_slot",
                    slot_id: bestSlotId,
                  })
                }
              >
                Select best slot
              </button>
            ) : null}
            <button
              type="button"
              onClick={() =>
                onAction("requester_decision", { action: "requester_cancel" })
              }
            >
              Cancel
            </button>
          </>
        ) : (
          <button type="button" onClick={() => onAction("cancel")}>
            Cancel
          </button>
        )}
        <a href="/kanban" aria-label="Open full Kanban task history">
          Kanban
        </a>
      </footer>
    </section>
  );
}
