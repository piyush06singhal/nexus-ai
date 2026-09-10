"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, MessageSquare, Users } from "lucide-react";
import type { AgentMessage, AgentReview } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

const MESSAGE_TYPE_LABELS: Record<string, string> = {
  task_assignment: "Task assignment",
  task_result: "Task result",
  request_information: "Request for info",
  information_response: "Information response",
  status_update: "Status update",
  error: "Error",
  review_request: "Review request",
  review_result: "Review result",
};

/**
 * Collaboration view for an orchestration: inter-agent messages, the shared
 * context entries, and agent reviews. Mirrors the WorkflowVisualization
 * styling (plain divs + StatusBadge, no extra dependencies).
 */
export function CollaborationView({
  messages,
  reviews,
  agentNames = {},
}: {
  messages: AgentMessage[];
  reviews: AgentReview[];
  agentNames?: Record<string, string>;
}) {
  return (
    <div className="space-y-6">
      <section>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          <MessageSquare className="h-3.5 w-3.5" />
          Agent messages
        </h3>
        {messages.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            No inter-agent messages exchanged during this run.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {messages.map((m) => (
              <MessageRow key={m.id} message={m} agentNames={agentNames} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          <Users className="h-3.5 w-3.5" />
          Agent reviews
        </h3>
        {reviews.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            No agent reviews requested for this orchestration.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {reviews.map((r) => (
              <ReviewRow key={r.id} review={r} agentNames={agentNames} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

const TYPE_COLOR: Record<string, string> = {
  task_assignment: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  task_result: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  request_information: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  information_response: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  status_update: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  review_request: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  review_result: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
};

function MessageTypeTag({ type }: { type: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${
        TYPE_COLOR[type] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
      }`}
    >
      {type.replace(/_/g, " ")}
    </span>
  );
}

function agentLabel(id: string | null, agentNames: Record<string, string>): string {
  if (!id) return "orchestrator";
  return agentNames[id] ?? `agent ${id.slice(0, 8)}`;
}

function MessageRow({
  message,
  agentNames,
}: {
  message: AgentMessage;
  agentNames: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const sender = agentLabel(message.sender_agent_id, agentNames);
  const recipient = agentLabel(message.recipient_agent_id, agentNames);

  return (
    <li className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        )}
        <span className="min-w-0 flex-1">
          <span className="truncate text-sm font-medium capitalize text-zinc-900 dark:text-zinc-100">
            {MESSAGE_TYPE_LABELS[message.message_type] ?? message.message_type}
          </span>
          <span className="ml-2 text-xs text-zinc-400">
            {sender} → {recipient}
          </span>
        </span>
        <MessageTypeTag type={message.message_type} />
      </button>
      {expanded && (
        <div className="border-t border-zinc-100 px-3 pb-3 pt-2 dark:border-zinc-800">
          <p className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
            {message.content || "—"}
          </p>
          {(message.metadata || message.correlation_id) && (
            <p className="mt-2 font-mono text-[11px] text-zinc-400">
              {message.correlation_id && (
                <>correlation: {message.correlation_id.slice(0, 8)} </>
              )}
              {message.metadata ? JSON.stringify(message.metadata) : ""}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function ReviewRow({
  review,
  agentNames,
}: {
  review: AgentReview;
  agentNames: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const reviewer = agentLabel(review.reviewer_agent_id, agentNames);
  const reviewee = review.reviewee_agent_id
    ? agentLabel(review.reviewee_agent_id, agentNames)
    : "a task";

  return (
    <li className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        )}
        <span className="min-w-0 flex-1 text-sm text-zinc-900 dark:text-zinc-100">
          <span className="font-medium">{reviewer}</span>{" "}
          <span className="text-zinc-400">reviewed</span> {reviewee}
          {review.iteration > 0 && (
            <span className="ml-2 text-[11px] text-zinc-400">
              iteration {review.iteration}
            </span>
          )}
        </span>
        <StatusBadge status={review.verdict} />
      </button>
      {expanded && (
        <div className="grid gap-3 border-t border-zinc-100 px-3 pb-3 pt-2 sm:grid-cols-2 dark:border-zinc-800">
          {review.request_content && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Request
              </p>
              <p className="mt-0.5 text-sm text-zinc-700 dark:text-zinc-300">
                {review.request_content}
              </p>
            </div>
          )}
          {review.response_content && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Response
              </p>
              <p className="mt-0.5 text-sm text-zinc-700 dark:text-zinc-300">
                {review.response_content}
              </p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}