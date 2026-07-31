import type { ActiveUserItem } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface ActiveUsersTableProps {
  users: ActiveUserItem[];
}

export function ActiveUsersTable({ users }: ActiveUsersTableProps) {
  if (users.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-[var(--muted)]">
        No user activity yet.
      </div>
    );
  }

  return (
    <div className="overflow-hidden border border-[var(--ink)]">
      <table className="w-full text-left text-sm">
        <thead
          className="bg-[var(--paper-deep)] text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]"
          style={{ fontFamily: '"JetBrains Mono", monospace' }}
        >
          <tr>
            <th className="px-3 py-2">User</th>
            <th className="px-3 py-2 text-right">Questions asked</th>
            <th className="px-3 py-2 text-right">Negative feedback</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--paper-deep)]">
          {users.map((user) => (
            <tr
              key={user.pseudonymous_user_id}
              className="cursor-pointer transition hover:bg-[var(--paper-deep)]/60"
              onClick={() => navigateToLogsWithFilter("user", user.display_name)}
              title="View this user's questions in Logs"
            >
              <td className="px-3 py-2 text-[var(--ink-soft)] underline decoration-[var(--muted)]/40">
                {user.display_name}
              </td>
              <td className="px-3 py-2 text-right font-medium text-[var(--ink)]">
                {user.interaction_count}
              </td>
              <td className="px-3 py-2 text-right text-[var(--muted)]">
                {user.negative_feedback_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
