import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, Command, LoaderCircle, LockKeyhole } from 'lucide-react';

type LoginPageProps = {
  loading: boolean;
  error: string | null;
  onLogin: (identity: string, password: string) => Promise<void>;
};

export function LoginPage({ loading, error, onLogin }: LoginPageProps) {
  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    try {
      await onLogin(identity.trim(), password);
      setPassword('');
    } catch (error) {
      setLocalError(error instanceof Error && error.message.includes('Cannot reach')
        ? 'The Helpdesk server is unavailable. Please try again when it is running.'
        : 'Unable to sign in with those credentials. Check your login identity and password, then try again.');
      setPassword('');
    }
  };

  return <main className="auth-screen">
    <section className="auth-card" aria-labelledby="login-title">
      <div className="auth-brand"><span className="brand-mark"><Command size={19}/><i /></span><span><strong>Helpdesk AI</strong><small>IT OPERATIONS</small></span></div>
      <div className="auth-heading"><span className="auth-icon"><LockKeyhole size={19}/></span><p className="eyebrow">SECURE WORKSPACE</p><h1 id="login-title">Welcome back</h1><p>Sign in to continue to your IT support workspace.</p></div>
      {(error || localError) && <div className="auth-error" role="alert">{localError || error}</div>}
      <form className="auth-form" onSubmit={submit}>
        <label htmlFor="login-identity">Login identity</label>
        <input id="login-identity" name="login_identity" type="text" autoComplete="username" required maxLength={254} value={identity} onChange={(event) => setIdentity(event.target.value)} disabled={loading}/>
        <label htmlFor="login-password">Password</label>
        <input id="login-password" name="password" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} disabled={loading}/>
        <button className="button button-primary auth-submit" type="submit" disabled={loading || !identity.trim() || !password}>
          {loading ? <><LoaderCircle size={16} className="spin"/> Signing in…</> : <>Sign in <ArrowRight size={16}/></>}
        </button>
      </form>
      <div className="auth-foot"><Activity size={14}/> Your session is protected by the Helpdesk server.</div>
    </section>
  </main>;
}
