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

const queryClient = new QueryClient();

function Router() {
  return (
    <RoutedErrorBoundary>
      <div className="flex min-h-screen bg-[#0d0d21] text-white">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <Switch>
            <Route path="/"            component={Dashboard}  />
            <Route path="/hitters"     component={Hitters}    />
            <Route path="/cc-tools"    component={CcTools}    />
            <Route path="/generators"  component={Generators} />
            <Route path="/wallet"      component={Wallet}     />
            <Route path="/admin"       component={Admin}      />
            <Route                     component={NotFound}   />
          </Switch>
        </main>
      </div>
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
