import type { CurrentUser, Member, Role } from '../../api/types';
import { ErrorState, LoadingState } from '../../components/data/states';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Select } from '../../components/ui/Select';
import { PageHeader } from '../../layouts/PageHeader';
import { formatDate } from '../../lib/format';
import { FormAlert } from '../auth/FormAlert';
import { toFormErrors } from '../auth/formErrors';
import { assignableRoles, canManageMember, ROLE_LABELS } from '../auth/permissions';
import { useCurrentUser } from '../auth/queries';
import { RequirePermission } from '../auth/RequireAuth';
import { AddMemberForm } from './AddMemberForm';
import { useMembers, useUpdateMember } from './queries';

export function TeamPage() {
  return (
    <RequirePermission permission="MANAGE_USERS">
      <Team />
    </RequirePermission>
  );
}

function Team() {
  const me = useCurrentUser().data as CurrentUser;
  const members = useMembers();
  const update = useUpdateMember();
  const updateError = toFormErrors(update.error).form;

  return (
    <>
      <PageHeader
        title="Team"
        description={`People in ${me.tenant.name}. Roles and access apply to this workspace only; the YouTube analytics data is shared by every workspace and is read-only.`}
      />

      <Card>
        <CardHeader
          title="Add a member"
          description="Creates an account in this workspace. Owners can add owners; admins can add admins and members."
        />
        <AddMemberForm actorRole={me.user.role} />
      </Card>

      <Card>
        <CardHeader
          title="Members"
          description="Deactivating someone signs them out everywhere and blocks sign-in."
        />
        {updateError && (
          <div className="px-4 pt-3">
            <FormAlert message={updateError} />
          </div>
        )}
        {members.isPending ? (
          <LoadingState label="Loading members" />
        ) : members.isError ? (
          <ErrorState error={members.error} onRetry={() => void members.refetch()} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-slate-100 text-xs text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Member
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Role
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Last sign-in (UTC)
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {members.data.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    actorRole={me.user.role}
                    isSelf={member.id === me.user.id}
                    busy={update.isPending}
                    onChange={(body) => update.mutate({ userId: member.id, body })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function MemberRow({
  member,
  actorRole,
  isSelf,
  busy,
  onChange,
}: {
  member: Member;
  actorRole: Role;
  isSelf: boolean;
  busy: boolean;
  onChange: (body: { role?: Role; is_active?: boolean }) => void;
}) {
  const editable = !isSelf && canManageMember(actorRole, member.role);
  return (
    <tr>
      <td className="px-4 py-2.5">
        <p className="font-medium text-slate-900">
          {member.display_name}
          {isSelf && <span className="ml-1.5 text-xs font-normal text-slate-500">(you)</span>}
        </p>
        <p className="text-xs text-slate-500">{member.email}</p>
      </td>
      <td className="px-4 py-2.5">
        {editable ? (
          <Select
            label={`Role for ${member.display_name}`}
            value={member.role}
            options={assignableRoles(actorRole).map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
            onChange={(role) => onChange({ role })}
            disabled={busy}
          />
        ) : (
          <Badge tone={member.role === 'OWNER' ? 'accent' : 'neutral'}>
            {ROLE_LABELS[member.role]}
          </Badge>
        )}
      </td>
      <td className="px-4 py-2.5">
        <Badge tone={member.is_active ? 'positive' : 'negative'}>
          {member.is_active ? 'Active' : 'Deactivated'}
        </Badge>
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-600">
        {member.last_login_at ? formatDate(member.last_login_at.slice(0, 10)) : 'Never'}
      </td>
      <td className="px-4 py-2.5 text-right">
        {editable && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            aria-label={`${member.is_active ? 'Deactivate' : 'Reactivate'} ${member.display_name}`}
            onClick={() => onChange({ is_active: !member.is_active })}
          >
            {member.is_active ? 'Deactivate' : 'Reactivate'}
          </Button>
        )}
      </td>
    </tr>
  );
}
