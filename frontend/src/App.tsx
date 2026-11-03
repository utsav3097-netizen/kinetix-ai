import { ArrowLeft, RefreshCw } from 'lucide-react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { ApiHealth } from './components/ApiHealth';
import { KinetixLogo } from './components/KinetixLogo';
import { Dashboard } from './features/account/Dashboard';
import { AuthPage } from './features/auth/AuthPage';
import { useAuth } from './features/auth/AuthProvider';
import { AnonymousRoute, ProtectedRoute } from './features/auth/ProtectedRoute';
import { OnboardingPage } from './features/profile/OnboardingPage';
import { RequireOnboarding } from './features/profile/RequireOnboarding';
import { LibraryPage } from './features/library/LibraryPage';
import { WorkoutsPage } from './features/workouts/WorkoutsPage';
import { NutritionPage } from './features/nutrition/NutritionPage';
import { ReportsPage } from './features/plans/ReportsPage';
import { PlansPage } from './features/plans/PlansPage';

function SessionStatus() {
  const { loading, initializationError, retryInitialization } = useAuth();
  if (loading) {
    return (
      <main id="main-content" className="session-loading" aria-busy="true">
        <RefreshCw className="loading-icon" size={28} aria-hidden="true" />
        <h1>Checking your session.</h1>
        <p role="status">Securely restoring your account…</p>
      </main>
    );
  }
  return (
    <main id="main-content" className="welcome">
      <section className="intro" aria-labelledby="session-error-heading">
        <span className="eyebrow"><span className="eyebrow-line" /> CONNECTION INTERRUPTED</span>
        <h1 id="session-error-heading">Let's <span>reconnect.</span></h1>
        <p className="intro-copy">We could not check your session. This does not mean you are logged out.</p>
        <div className="error-notice" role="alert">{initializationError}</div>
        <button type="button" className="primary-button retry-session" onClick={retryInitialization}><RefreshCw size={17} aria-hidden="true" />Try again</button>
      </section>
      <ApiHealth />
    </main>
  );
}

export default function App() {
  const { user, loading, initializationError } = useAuth();
  const ready = !loading && !initializationError;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="site-header">
        <Link to="/" className="brand" aria-label="KINETIX AI home">
          <KinetixLogo className="brand-logo" aria-hidden="true" />
          <span>KINETIX <span className="brand-accent">AI</span></span>
        </Link>
        {ready ? (
          <nav className="header-nav" aria-label="Main navigation">
            {user ? <><NavLink to="/" end>Dashboard</NavLink><NavLink to="/workouts">Workouts</NavLink><NavLink to="/nutrition">Nutrition</NavLink><NavLink to="/reports">Reports</NavLink><NavLink to="/plans">Plans</NavLink><NavLink to="/onboarding">Profile</NavLink><NavLink to="/library">Library</NavLink></> : (
              <>
                <NavLink to="/login">Log in</NavLink>
                <NavLink to="/register">Register</NavLink>
              </>
            )}
          </nav>
        ) : <span className="header-caption">BUILT FOR ATHLETES</span>}
      </header>
      {!ready ? <SessionStatus /> : (
        <Routes>
          <Route element={<AnonymousRoute />}>
            <Route path="/login" element={<AuthPage key="login" mode="login" />} />
            <Route path="/register" element={<AuthPage key="register" mode="register" />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route element={<RequireOnboarding />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/workouts" element={<WorkoutsPage />} />
              <Route path="/nutrition" element={<NutritionPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/plans" element={<PlansPage />} />
            </Route>
          </Route>
          <Route path="*" element={
            <main id="main-content" className="not-found">
              <h1>Page not found.</h1>
              <p>This address does not have a page.</p>
              <Link to="/" className="home-link"><ArrowLeft size={18} aria-hidden="true" />Return home</Link>
            </main>
          } />
        </Routes>
      )}
      <footer className="site-footer"><span>KINETIX AI</span><span>Precision. Purpose. Progress.</span></footer>
    </div>
  );
}
