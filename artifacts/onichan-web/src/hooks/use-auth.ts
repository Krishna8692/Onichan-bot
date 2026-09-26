import { useEffect, useState } from 'react';
import { getMe, type MeResponse } from '@/lib/api';

export function useAuth() {
  const [user, setUser] = useState<MeResponse | null | undefined>(undefined);

  useEffect(() => {
    getMe().then(setUser);
  }, []);

  return {
    user,
    loading: user === undefined,
    loggedIn: !!user,
    isAdmin: !!user?.is_admin,
  };
}
