import { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Sidebar } from '@/components/sidebar';
import Dashboard from '@/pages/dashboard';
import Hitters from '@/pages/hitters';
import CcTools from '@/pages/cc-tools';
import Generators from '@/pages/generators';
import Wallet from '@/pages/wallet';
import Admin from '@/pages/admin';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';
import { AppLayout } from '@/components/AppLayout';
import { AuthGuard } from '@/components/AuthGuard';
import DashboardPage from '@/pages/DashboardPage';
import HitterPage from '@/pages/HitterPage';
import CCToolsPage from '@/pages/CCToolsPage';
import WalletPage from '@/pages/WalletPage';
import AdminPage from '@/pages/AdminPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

function WithLayout({ children }: { children: ReactNode }) {
  return (
    <AppLayout>
      {children}
    </AppLayout>
  );
}

function Router() {
  return (
    <RoutedErrorBoundary>
      <Switch>
        {/* Dashboard */}
        <Route path="/">
          {() => (
            <WithLayout>
              <AuthGuard><DashboardPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        <Route path="/dashboard">
          {() => (
            <WithLayout>
              <AuthGuard><DashboardPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        {/* Hitters */}
        <Route path="/hitters/:gateway">
          {() => (
            <WithLayout>
              <AuthGuard><HitterPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        {/* CC Tools */}
        <Route path="/tools/gen">
          {() => (
            <WithLayout>
              <AuthGuard><CCToolsPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        <Route path="/tools/fake">
          {() => (
            <WithLayout>
              <AuthGuard><CCToolsPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        <Route path="/tools/iban">
          {() => (
            <WithLayout>
              <AuthGuard><CCToolsPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        <Route path="/tools/clean">
          {() => (
            <WithLayout>
              <AuthGuard><CCToolsPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        <Route path="/tools/pick">
          {() => (
            <WithLayout>
              <AuthGuard><CCToolsPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        {/* Wallet */}
        <Route path="/wallet">
          {() => (
            <WithLayout>
              <AuthGuard><WalletPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        {/* Admin */}
        <Route path="/admin">
          {() => (
            <WithLayout>
              <AuthGuard requireAdmin><AdminPage /></AuthGuard>
            </WithLayout>
          )}
        </Route>

        {/* 404 */}
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
