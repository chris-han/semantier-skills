export type NegotiationCardProps = {
  taskId: string;
  extensionId: string;
  negotiationId?: string;
  metadata: Record<string, unknown>;
  onOpenDetail: () => void;
  onAction: (actionId: string, payload?: Record<string, unknown>) => void;
  compact?: boolean;
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

export default function NegotiationCard({
  negotiationId,
  metadata,
  onOpenDetail,
  onAction,
}: NegotiationCardProps) {
  const title = text(metadata.meeting_title, "Meeting negotiation");
  const status = text(metadata.status, "pending");
  const followupStatus = text(metadata.followup_cron_status, "not_created");
  const nextFollowupAt = text(metadata.next_followup_at, "not scheduled");
  const lastTickAt = text(metadata.followup_cron_last_tick_at, "never");
  const failureCount = safeCount(metadata.followup_cron_failure_count, 0);
  const declinedAttendee = text(metadata.declined_attendee_name, "Declined attendee");
  const missingAttendees = asStringArray(metadata.missing_required_attendee_names);
  const bestSlot = text(metadata.best_slot, "No candidate slot");
  const bestSlotId = text(metadata.best_slot_id);
  const showRequesterActions = status === "awaiting_requester_decision";

  return (
    <div
      className="feishu-meeting-negotiation-card"
      data-negotiation-id={negotiationId}
    >
      <div className="feishu-meeting-negotiation-card__header">
        <strong>{title}</strong>
        <span>{status}</span>
      </div>
      <div>Declined attendee: {declinedAttendee}</div>
      <div>Cron: {followupStatus}</div>
      <div>Next follow-up: {nextFollowupAt}</div>
      <div>Last tick: {lastTickAt}</div>
      <div>Cron failures: {failureCount}</div>
      <div>Best slot: {bestSlot}</div>
      <div>
        Missing required attendees:{" "}
        {missingAttendees.length > 0 ? missingAttendees.join(", ") : "none"}
      </div>
      <div className="feishu-meeting-negotiation-card__actions">
        <button type="button" onClick={onOpenDetail}>
          Open
        </button>
        <button type="button" onClick={() => onAction("nudge_unblock")}>
          Nudge
        </button>
        <a href="/kanban" aria-label="Open full Kanban task history">
          Kanban
        </a>
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
        ) : null}
        {!showRequesterActions ? (
          <button type="button" onClick={() => onAction("cancel")}>
            Cancel
          </button>
        ) : null}
        <button type="button" onClick={() => onAction("finalize")}>
          Finalize
        </button>
      </div>
    </div>
  );
}
