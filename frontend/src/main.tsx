import '@fontsource-variable/inter';
import './styles/index.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter } from 'react-router';

import App from './App';
import { routes } from './app/routes';
import { createQueryClient } from './query';

const root = document.getElementById('root');
if (!root) {
  throw new Error('Root element #root not found');
}

const queryClient = createQueryClient();
const router = createBrowserRouter(routes);

createRoot(root).render(
  <StrictMode>
    <App router={router} queryClient={queryClient} />
  </StrictMode>,
);
