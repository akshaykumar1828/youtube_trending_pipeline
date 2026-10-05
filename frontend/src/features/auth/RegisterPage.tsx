import { useState, type FormEvent } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router';

import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { TextField } from '../../components/ui/TextField';
import { APP_NAME } from '../../layouts/PageHeader';
import { FormAlert } from './FormAlert';
import { toFormErrors } from './formErrors';
import { MIN_PASSWORD_LENGTH, passwordProblem } from './passwordPolicy';
import { safeNextPath } from './permissions';
import { useCurrentUser, useRegister } from './queries';

export function RegisterPage() {
  const [params] = useSearchParams();
  const next = safeNextPath(params.get('next'));
  const currentUser = useCurrentUser();
  const register = useRegister();
  const [values, setValues] = useState({
    display_name: '',
    email: '',
    password: '',
    tenant_name: '',
  });
  const [passwordError, setPasswordError] = useState<string | undefined>();

  if (currentUser.data) return <Navigate to={next} replace />;

  const errors = toFormErrors(register.error);
  const set = (field: keyof typeof values) => (value: string) => {
    setValues((v) => ({ ...v, [field]: value }));
    if (field === 'password') setPasswordError(undefined);
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const problem = passwordProblem(values.password);
    if (problem) {
      setPasswordError(problem);
      return;
    }
    register.mutate({
      display_name: values.display_name,
      email: values.email,
      password: values.password,
      tenant_name: values.tenant_name.trim() || null,
    });
  };

  return (
    <Card className="p-6">
      <title>{`Create a workspace · ${APP_NAME}`}</title>
      <h1 className="text-lg font-semibold text-slate-900">Create a workspace</h1>
      <p className="mt-1 text-sm text-slate-600">
        You become the workspace owner and can add your team afterwards.
      </p>
      <form className="mt-5 space-y-4" onSubmit={onSubmit}>
        <FormAlert message={errors.form} />
        <TextField
          label="Your name"
          name="display_name"
          autoComplete="name"
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
          autoComplete="email"
          required
          maxLength={254}
          value={values.email}
          onChange={set('email')}
          error={errors.fields.email}
        />
        <TextField
          label="Password"
          type="password"
          name="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={128}
          value={values.password}
          onChange={set('password')}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. A passphrase works well.`}
          error={passwordError ?? errors.fields.password}
        />
        <TextField
          label="Workspace name (optional)"
          name="tenant_name"
          autoComplete="organization"
          maxLength={100}
          value={values.tenant_name}
          onChange={set('tenant_name')}
          error={errors.fields.tenant_name}
        />
        <Button type="submit" variant="primary" className="w-full" disabled={register.isPending}>
          {register.isPending ? 'Creating…' : 'Create workspace'}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        Already have an account?{' '}
        <Link
          to={{ pathname: '/login', search: params.toString() ? `?${params}` : '' }}
          className="font-medium text-accent-700 hover:underline"
        >
          Sign in
        </Link>
      </p>
    </Card>
  );
}
