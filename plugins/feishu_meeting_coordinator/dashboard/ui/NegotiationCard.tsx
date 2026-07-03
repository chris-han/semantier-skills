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

export default function NegotiationCard({
  negotiationId,
  metadata,
  onOpenDetail,
  onAction,
}: NegotiationCardProps) {
  const title = text(metadata.meeting_title, "Meeting negotiation");
  const status = text(metadata.status, "pending");
  const declinedAttendee = text(
    metadata.declined_attendee_name,
    "Declined attendee",
  );

  return (
    <div
      className="feishu-meeting-negotiation-card"
      data-negotiation-id={negotiationId}
    >
      <div className="feishu-meeting-negotiation-card__header">
        <strong>{title}</strong>
        <span>{status}</span>
      </div>
      <div>{declinedAttendee}</div>
      <div className="feishu-meeting-negotiation-card__actions">
        <button type="button" onClick={onOpenDetail}>
          Open
        </button>
        <button type="button" onClick={() => onAction("nudge_unblock")}>
          Nudge
        </button>
        <button type="button" onClick={() => onAction("finalize")}>
          Finalize
        </button>
        <button type="button" onClick={() => onAction("cancel")}>
          Cancel
        </button>
        <a href="/kanban" aria-label="Open full Kanban task history">
          Kanban
        </a>
      </div>
    </div>
  );
}
