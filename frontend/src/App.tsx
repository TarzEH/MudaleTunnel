import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { CommandPalette } from './components/CommandPalette';
import { AuthProvider, useAuth } from './context/AuthContext';
import { EngagementProvider } from './context/EngagementContext';
import { SocketProvider, useSocket } from './context/SocketContext';
import { ThemeProvider } from './context/ThemeContext';
import { Login } from './pages/Login';
import { Sessions } from './pages/Sessions';
import { TunnelDetail } from './pages/TunnelDetail';
import { Topology } from './pages/Topology';
import { Scans } from './pages/Scans';
import { Agents } from './pages/Agents';
import { Audit } from './pages/Audit';
import { Engagements } from './pages/Engagements';
import { Settings } from './pages/Settings';

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { connectionState } = useSocket();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const isMeta = e.metaKey || e.ctrlKey;
      if (isMeta && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (e.key === '/' && !isTypingTarget(e.target) && !paletteOpen) {
        const el = document.querySelector<HTMLElement>('[data-filter-focus]');
        if (el) {
          e.preventDefault();
          el.focus();
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [paletteOpen]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-base text-text-primary">
      <Sidebar connectionState={connectionState} />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Sessions />} />
          <Route path="/tunnels/:id" element={<TunnelDetail />} />
          <Route path="/topology" element={<Topology />} />
          <Route path="/scans" element={<Scans />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/engagements" element={<Engagements />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

/**
 * Auth boundary. Nothing that talks to the API — including the WebSocket — is
 * mounted until the server has confirmed who the operator is, so an
 * unauthenticated visitor never triggers a burst of 403s or sees a half-rendered
 * shell of a tool that manages access to client networks.
 */
function Gate() {
  const { me, loading, setMe } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base">
        <span className="text-sm text-text-muted">Loading…</span>
      </div>
    );
  }

  if (!me) {
    return <Login onSignedIn={setMe} />;
  }

  return (
    <EngagementProvider>
      <SocketProvider>
        <Shell />
      </SocketProvider>
    </EngagementProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </ThemeProvider>
  );
}
