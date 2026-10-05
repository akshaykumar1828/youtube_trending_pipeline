import { useState, type FormEvent } from 'react';

import type { Role } from '../../api/types';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { TextField } from '../../components/ui/TextField';
import { FormAlert } from '../auth/FormAlert';
import { toFormErrors } from '../auth/formErrors';
import { MIN_PASSWORD_LENGTH, passwordProblem } from '../auth/passwordPolicy';
import { assignableRoles, ROLE_LABELS } from '../auth/permissions';
import { useCreateMember } from './queries';

const EMPTY = { display_name: '', email: '', password: '' };

/** Adds a user to the caller's workspace with an initial password (shared out of band). */
export function AddMemberForm({ actorRole }: { actorRole: Role }) {
  const create = useCreateMember();
  const [values, setValues] = useState(EMPTY);
  const [role, setRole] = useState<Role>('MEMBER');
  const [passwordError, setPasswordError] = useState<string | undefined>();
  const [added, setAdded] = useState<string | null>(null);
  const errors = toFormErrors(create.error);
  const roleOptions = assignableRoles(actorRole).map((r) => ({ value: r, label: ROLE_LABELS[r] }));

  const set = (field: keyof typeof EMPTY) => (value: string) => {
    setValues((v) => ({ ...v, [field]: value }));
    setAdded(null);
    if (field === 'password') setPasswordError(undefined);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const problem = passwordProblem(values.password);
    if (problem) {
      setPasswordError(problem);
      return;
    }
    create.mutate(
      { ...values, role },
      {
        onSuccess: (response) => {
          setValues(EMPTY);
          setRole('MEMBER');
          setAdded(`${response.data.email} was added as ${ROLE_LABELS[response.data.role]}.`);
        },
      },
    );
  };

  return (
    <form className="space-y-3 p-4" onSubmit={onSubmit} aria-label="Add a member">
      <FormAlert message={errors.form} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <TextField
          label="Name"
          name="display_name"
          autoComplete="off"
          required
          maxLength={100}
          value={values.display_name}
          onChange={set('display_name')}
          error={errors.fields.display_name}
        />
        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="off"
          required
          maxLength={254}
          value={values.email}
          onChange={set('email')}
          error={errors.fields.email}
        />
        <TextField
          label="Initial password"
          type="password"
          name="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={128}
          value={values.password}
          onChange={set('password')}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. Share it privately.`}
          error={passwordError ?? errors.fields.password}
        />
        <div className="flex items-end">
          <Select
            label="Role"
            showLabel
            value={role}
            options={roleOptions}
            onChange={setRole}
            className="h-9 text-sm"
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={create.isPending}>
          {create.isPending ? 'Adding…' : 'Add member'}
        </Button>
        {added && (
          <p role="status" className="text-sm text-emerald-700">
            {added}
          </p>
        )}
      </div>
    </form>
  );
}
