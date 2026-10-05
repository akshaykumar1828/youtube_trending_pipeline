import { Outlet } from 'react-router';

import { Brand } from '../../layouts/Sidebar';

/** Frame for the public sign-in and registration pages (no app navigation). */
export function AuthLayout() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-10">
      <div className="mb-6">
        <Brand />
      </div>
      <div className="w-full max-w-sm">
        <Outlet />
      </div>
    </main>
  );
}
