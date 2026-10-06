import { Outlet } from 'react-router';

import { Logo } from '../../layouts/Logo';
import { APP_NAME } from '../../layouts/PageHeader';

/** Frame for the public sign-in and registration pages (no app navigation). */
export function AuthLayout() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-red-50 via-white to-slate-50 px-4 py-10">
      <div className="mb-8 flex max-w-xl flex-col items-center text-center">
        <div className="mb-4">
          <Logo size="lg" />
        </div>
        {/* Not a heading element: each page keeps its own h1 (Sign in / Create a workspace). */}
        <p className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{APP_NAME}</p>
        <p className="mt-2 text-sm text-slate-600 sm:text-base">
          Trending analytics and high-performance predictions for YouTube videos.
        </p>
      </div>
      <div className="w-full max-w-sm *:shadow-xl *:shadow-slate-200/70">
        <Outlet />
      </div>
    </main>
  );
}
