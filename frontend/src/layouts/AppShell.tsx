import * as Dialog from '@radix-ui/react-dialog';
import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import { Outlet } from 'react-router';

import { Button } from '../components/ui/Button';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

/** Application frame: fixed sidebar on large screens, drawer navigation below `lg`. */
export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="min-h-screen lg:pl-60">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-white px-3 py-2 text-sm focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>

      <aside className="fixed inset-y-0 left-0 hidden w-60 border-r border-slate-200 bg-white lg:block">
        <Sidebar />
      </aside>

      <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/30 lg:hidden" />
          <Dialog.Content
            aria-describedby={undefined}
            className="fixed inset-y-0 left-0 z-50 w-64 border-r border-slate-200 bg-white lg:hidden"
          >
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Close asChild>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Close navigation"
                className="absolute top-3 right-3"
              >
                <X aria-hidden="true" className="size-4" />
              </Button>
            </Dialog.Close>
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>

        <Header
          menuButton={
            <Dialog.Trigger asChild>
              <Button variant="ghost" size="sm" aria-label="Open navigation" className="lg:hidden">
                <Menu aria-hidden="true" className="size-5" />
              </Button>
            </Dialog.Trigger>
          }
        />
      </Dialog.Root>

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 outline-none sm:px-6"
      >
        <Outlet />
      </main>
    </div>
  );
}
