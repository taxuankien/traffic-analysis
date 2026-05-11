import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './components/Toast';
import App from './App';
import SourcesPage from './pages/SourcesPage';
import ROIEditorPage from './pages/ROIEditorPage';
import AnalysisPage from './pages/AnalysisPage';
import ResultsPage from './pages/ResultsPage';
import InferenceSettingsPage from './pages/InferenceSettingsPage';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <Routes>
            <Route element={<App />}>
              <Route index element={<Navigate to="/sources" replace />} />
              <Route path="sources" element={<SourcesPage />} />
              <Route path="sources/:sourceId/roi" element={<ROIEditorPage />} />
              <Route path="sources/:sourceId/analysis" element={<AnalysisPage />} />
              <Route path="sources/:sourceId/results" element={<ResultsPage />} />
              <Route path="settings/inference" element={<InferenceSettingsPage />} />
            </Route>
          </Routes>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
