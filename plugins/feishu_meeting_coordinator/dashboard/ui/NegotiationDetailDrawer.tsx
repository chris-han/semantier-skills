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

export default function NegotiationDetailDrawer({
  negotiationId,
  metadata,
  onAction,
  onClose,
}: NegotiationDetailDrawerProps) {
  const title = text(metadata.meeting_title, "Meeting negotiation");
  const status = text(metadata.status, "pending");

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
      </dl>
      <footer>
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
      </footer>
    </section>
  );
}
