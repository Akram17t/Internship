import type { ActiveUserItem, DateRange } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface ActiveUsersTableProps {
  users: ActiveUserItem[];
  dateRange?: DateRange;
}

export function ActiveUsersTable({ users, dateRange }: ActiveUsersTableProps) {
  if (users.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-[var(--muted)]">
        No user activity yet.
      </div>
    );
  }

  // Two columns only: the negative-feedback count already has its own KPI tile
  // and is broken out per day in the trend chart, so repeating it per user here
  // only squeezed the email column.
  //
  // table-fixed + a truncating User cell rather than overflow-x: this card sits
  // in a 1/3 track, and a long address like e2e.testuser@icscompute.com is wide
  // enough on its own to push the count column out of view behind an internal
  // scrollbar. The full address stays available as the cell's title.
  return (
    <table className="w-full table-fixed border-collapse text-left text-sm">
      <thead className="bg-[var(--paper-deep)] text-[11px] text-[var(--muted)]">
        <tr>
          <th className="border-b border-[var(--line)] py-2.5 pr-3 pl-3 font-normal">User</th>
          <th className="w-24 border-b border-[var(--line)] py-2.5 pr-3 text-right font-normal">
            Questions
          </th>
        </tr>
      </thead>
      <tbody>
        {users.map((user) => (
          <tr
            key={user.pseudonymous_user_id}
            className="group cursor-pointer border-b border-[var(--line-soft)] transition last:border-b-0 hover:bg-[rgba(188,24,35,0.045)]"
            onClick={() => navigateToLogsWithFilter("user", user.display_name, undefined, dateRange)}
            title="View this user's questions in Logs"
          >
            <td className="border-l-4 border-transparent py-3 pr-3 pl-3 transition-colors group-hover:border-l-[var(--red)]">
              <span
                className="block truncate text-[15px] text-[var(--ink)]"
                title={user.display_name}
              >
                {user.display_name}
              </span>
            </td>
            <td className="py-3 pr-3 text-right font-mono tabular-nums text-[var(--ink)]">
              {user.interaction_count}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
