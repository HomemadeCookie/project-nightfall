/**
 * Entry point.
 *
 * StrictMode is on. It double-invokes effects in development, which is exactly the pressure
 * the map lifecycle needs: a map or worker that leaks on remount shows up here rather than in
 * a user's tab after an hour.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { terminateDecodeWorker } from './workers/client';

import './styles.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Artifacts are immutable and content-hashed; the manifest is refetched on demand, so
      // there is nothing for a background refetch to discover.
      refetchOnWindowFocus: false,
      staleTime: Number.POSITIVE_INFINITY,
    },
  },
});

const container = document.getElementById('root');
if (container === null) {
  throw new Error('#root is missing from the document');
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);

window.addEventListener('pagehide', terminateDecodeWorker);
