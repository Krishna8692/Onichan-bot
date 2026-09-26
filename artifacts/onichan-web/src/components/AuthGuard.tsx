import { type ReactNode, useEffect } from 'react';
import { useLocation } from 'wouter';
import { useAuth } from '@/hooks/use-auth';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

export function AuthGuard({ children, requireAdmin = false }: { children: ReactNode; requireAdmin?: boolean }) {
  const { user, loading, loggedIn, isAdmin } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (loading) return;
    if (!loggedIn) {
      window.location.href = `${BASE}/user/login`;
      return;
    }
    if (requireAdmin && !isAdmin) {
      navigate('/dashboard');
    }
  }, [loading, loggedIn, isAdmin, requireAdmin]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin h-8 w-8 border-4 border-purple-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!loggedIn) return null;
  if (requireAdmin && !isAdmin) return null;

  return <>{children}</>;
}
