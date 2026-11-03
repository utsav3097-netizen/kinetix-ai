import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link, useLocation } from 'react-router-dom';
import { z } from 'zod';
import { ApiError } from '../../lib/api';
import type { Credentials } from '../../lib/api';
import { useAuth } from './AuthProvider';

const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email('Enter a valid email address.').max(254, 'Email must be 254 characters or fewer.'),
  password: z.string().min(8, 'Use at least 8 characters.').max(128, 'Use no more than 128 characters.'),
});

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const signingUp = mode === 'register';
  const auth = useAuth();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const { register, handleSubmit, setError, resetField, formState: { errors, isSubmitting } } = useForm<Credentials>({
    resolver: zodResolver(credentialsSchema),
    defaultValues: { email: '', password: '' },
  });

  const submit = handleSubmit(async (credentials) => {
    setServerError(null);
    try {
      if (signingUp) await auth.register(credentials);
      else await auth.login(credentials);
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Unable to sign in. Please try again.');
      if (error instanceof ApiError) {
        for (const field of ['email', 'password'] as const) {
          if (error.fieldErrors[field]) setError(field, { message: error.fieldErrors[field] }, { shouldFocus: true });
        }
      }
    } finally {
      resetField('password', { keepError: true });
    }
  });

  return (
    <main id="main-content" className="welcome auth-layout">
      <section className="intro" aria-labelledby="auth-intro-heading">
        <span className="eyebrow"><span className="eyebrow-line" /> THE ATHLETE PLATFORM</span>
        <h1 id="auth-intro-heading">Your journey.<br /><span>Your account.</span></h1>
        <p className="intro-copy">A dedicated space for your athletic journey. Start with a secure KINETIX AI account.</p>
        <div className="security-note"><ShieldCheck size={19} aria-hidden="true" /><span>Use a long, unique password to help keep your account secure.</span></div>
      </section>

      <section className="connection-card auth-card" aria-labelledby="auth-heading">
        <span className="card-label">{signingUp ? 'GET STARTED' : 'WELCOME BACK'}</span>
        <h2 id="auth-heading">{signingUp ? 'Create your account.' : 'Log in to KINETIX AI.'}</h2>
        <p>{signingUp ? 'Use your email and a strong, unique password.' : 'Pick up where you left off.'}</p>
        <form className="auth-form" onSubmit={(event) => void submit(event)} noValidate aria-busy={isSubmitting}>
          {serverError && <div className="error-notice" role="alert">{serverError}</div>}
          <div className="form-field">
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={254}
              required
              readOnly={isSubmitting}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'email-error' : undefined}
              {...register('email')}
            />
            {errors.email && <span id="email-error" className="field-error">{errors.email.message}</span>}
          </div>
          <div className="form-field">
            <label htmlFor="password">Password</label>
            <div className="password-input">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={signingUp ? 'new-password' : 'current-password'}
                minLength={8}
                maxLength={128}
                required
                readOnly={isSubmitting}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={`password-hint${errors.password ? ' password-error' : ''}`}
                {...register('password')}
              />
              <button type="button" className="password-toggle" onClick={() => setShowPassword((shown) => !shown)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>
                {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
              </button>
            </div>
            <span id="password-hint" className="field-hint">8–128 characters. A longer, unique password is recommended.</span>
            {errors.password && <span id="password-error" className="field-error">{errors.password.message}</span>}
          </div>
          <button type="submit" className="primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? (signingUp ? 'Creating account…' : 'Logging in…') : (signingUp ? 'Create account' : 'Log in')}</span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </form>
        <p className="auth-switch">
          {signingUp ? 'Already have an account? ' : 'New to KINETIX AI? '}
          <Link to={signingUp ? '/login' : '/register'} state={location.state}>{signingUp ? 'Log in' : 'Create an account'}</Link>
        </p>
      </section>
    </main>
  );
}
