import { useState, type FormEvent } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router';

import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { TextField } from '../../components/ui/TextField';
import { APP_NAME } from '../../layouts/PageHeader';
import { FormAlert } from './FormAlert';
import { toFormErrors } from './formErrors';
import { safeNextPath } from './permissions';
import { useCurrentUser, useLogin } from './queries';

export function LoginPage() {
  const [params] = useSearchParams();
  const next = safeNextPath(params.get('next'));
  const currentUser = useCurrentUser();
  const login = useLogin();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (currentUser.data) return <Navigate to={next} replace />;

  const errors = toFormErrors(login.error);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ email, password });
  };

  return (
    <Card className="p-6">
      <title>{`Sign in · ${APP_NAME}`}</title>
      <h1 className="text-lg font-semibold text-slate-900">Sign in</h1>
      <p className="mt-1 text-sm text-slate-600">Use your workspace account.</p>
      <form className="mt-5 space-y-4" onSubmit={onSubmit}>
        <FormAlert message={errors.form} />
        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          required
          maxLength={254}
          value={email}
          onChange={setEmail}
          error={errors.fields.email}
        />
        <TextField
          label="Password"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={password}
          onChange={setPassword}
          error={errors.fields.password}
        />
        <Button type="submit" variant="primary" className="w-full" disabled={login.isPending}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        No account?{' '}
        <Link
          to={{ pathname: '/register', search: params.toString() ? `?${params}` : '' }}
          className="font-medium text-accent-700 hover:underline"
        >
          Create a workspace
        </Link>
      </p>
    </Card>
  );
}
