import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/Shared";

const OverviewPage = lazy(async () => ({
  default: (await import("./pages/OverviewPage")).OverviewPage,
}));
const GeneratePage = lazy(async () => ({
  default: (await import("./pages/GeneratePage")).GeneratePage,
}));
const EvaluationPage = lazy(async () => ({
  default: (await import("./pages/EvaluationPage")).EvaluationPage,
}));
const HistoryPage = lazy(async () => ({
  default: (await import("./pages/HistoryPage")).HistoryPage,
}));
const NotesPage = lazy(async () => ({
  default: (await import("./pages/NotesPage")).NotesPage,
}));
const RejectionsPage = lazy(async () => ({
  default: (await import("./pages/DataPages")).RejectionsPage,
}));
const LearningPage = lazy(async () => ({
  default: (await import("./pages/DataPages")).LearningPage,
}));
const KnowledgePage = lazy(async () => ({
  default: (await import("./pages/DataPages")).KnowledgePage,
}));
const SettingsPage = lazy(async () => ({
  default: (await import("./pages/DataPages")).SettingsPage,
}));
const ProfilePage = lazy(async () => ({
  default: (await import("./pages/ProfilePage")).ProfilePage,
}));
const RunPage = lazy(async () => ({
  default: (await import("./pages/RunPages")).RunPage,
}));
const LessonPage = lazy(async () => ({
  default: (await import("./pages/RunPages")).LessonPage,
}));
const ReportPage = lazy(async () => ({
  default: (await import("./pages/RunPages")).ReportPage,
}));

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          index
          element={<Suspense fallback={<LoadingState />}><OverviewPage /></Suspense>}
        />
        <Route path="generate" element={<Suspense fallback={<LoadingState />}><GeneratePage /></Suspense>} />
        <Route path="evaluation" element={<Suspense fallback={<LoadingState />}><EvaluationPage /></Suspense>} />
        <Route path="history" element={<Suspense fallback={<LoadingState />}><HistoryPage /></Suspense>} />
        <Route path="notes" element={<Suspense fallback={<LoadingState />}><NotesPage /></Suspense>} />
        <Route path="notes/:runId" element={<Suspense fallback={<LoadingState />}><NotesPage /></Suspense>} />
        <Route path="rejections" element={<Suspense fallback={<LoadingState />}><RejectionsPage /></Suspense>} />
        <Route path="learning" element={<Suspense fallback={<LoadingState />}><LearningPage /></Suspense>} />
        <Route path="knowledge" element={<Suspense fallback={<LoadingState />}><KnowledgePage /></Suspense>} />
        <Route path="settings" element={<Suspense fallback={<LoadingState />}><SettingsPage /></Suspense>} />
        <Route path="profile" element={<Suspense fallback={<LoadingState />}><ProfilePage /></Suspense>} />
        <Route path="runs/:runId" element={<Suspense fallback={<LoadingState />}><RunPage /></Suspense>} />
        <Route path="runs/:runId/lesson" element={<Suspense fallback={<LoadingState />}><LessonPage /></Suspense>} />
        <Route path="runs/:runId/report" element={<Suspense fallback={<LoadingState />}><ReportPage /></Suspense>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
