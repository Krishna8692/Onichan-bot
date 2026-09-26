import { type ReactNode } from 'react';
import { Link, useLocation } from 'wouter';
import {
  LayoutDashboard, Zap, CreditCard, Wand2, Wallet, ShieldCheck,
  ChevronRight, LogOut, Menu,
} from 'lucide-react';
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarProvider, SidebarTrigger,
} from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { useAuth } from '@/hooks/use-auth';
import { cn } from '@/lib/utils';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const HITTERS = [
  { label: 'Auto Hit', path: '/hitters/auto', icon: '⚡' },
  { label: 'Checkout.com', path: '/hitters/hitck', icon: '🛒' },
  { label: 'Adyen', path: '/hitters/hitad', icon: '🔵' },
  { label: 'MPGS', path: '/hitters/hitmpgs', icon: '🟠' },
  { label: 'Whop', path: '/hitters/hitwhop', icon: '🟣' },
  { label: 'Paddle', path: '/hitters/hitpad', icon: '🏓' },
  { label: 'Epoch', path: '/hitters/hitep', icon: '🔴' },
  { label: 'Jio', path: '/hitters/jio', icon: '📱' },
];

const CC_TOOLS = [
  { label: 'Generator', path: '/tools/gen' },
  { label: 'Fake ID', path: '/tools/fake' },
  { label: 'IBAN', path: '/tools/iban' },
  { label: 'Cleaner', path: '/tools/clean' },
  { label: 'Picker', path: '/tools/pick' },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const { user, isAdmin } = useAuth();

  function isActive(path: string) {
    return location === path || location.startsWith(path + '/');
  }

  return (
    <SidebarProvider defaultOpen={true}>
      <Sidebar collapsible="icon">
        <SidebarHeader className="p-3 border-b border-sidebar-border">
          <div className="flex items-center gap-2 px-1">
            <div className="w-8 h-8 rounded-lg bg-purple-600 flex items-center justify-center text-white font-bold text-sm">O</div>
            <div className="group-data-[collapsible=icon]:hidden">
              <p className="font-bold text-sm text-sidebar-foreground">Onichan</p>
              <p className="text-xs text-sidebar-foreground/60">Control Panel</p>
            </div>
          </div>
        </SidebarHeader>

        <SidebarContent>
          {/* Dashboard */}
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={isActive('/dashboard')}>
                  <Link href="/dashboard">
                    <LayoutDashboard size={16} />
                    <span>Dashboard</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>

          <Separator className="mx-2 w-auto bg-sidebar-border" />

          {/* Hitters */}
          <SidebarGroup>
            <SidebarGroupLabel className="flex items-center gap-1">
              <Zap size={12} />
              <span>Hitters</span>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {HITTERS.map((item) => (
                  <SidebarMenuItem key={item.path}>
                    <SidebarMenuButton asChild isActive={isActive(item.path)}>
                      <Link href={item.path}>
                        <span className="text-base leading-none">{item.icon}</span>
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <Separator className="mx-2 w-auto bg-sidebar-border" />

          {/* CC Tools */}
          <SidebarGroup>
            <SidebarGroupLabel className="flex items-center gap-1">
              <CreditCard size={12} />
              <span>CC Tools</span>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {CC_TOOLS.map((item) => (
                  <SidebarMenuItem key={item.path}>
                    <SidebarMenuButton asChild isActive={isActive(item.path)}>
                      <Link href={item.path}>
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <Separator className="mx-2 w-auto bg-sidebar-border" />

          {/* Wallet */}
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={isActive('/wallet')}>
                  <Link href="/wallet">
                    <Wallet size={16} />
                    <span>Wallet</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>

          {/* Admin — only for admins */}
          {isAdmin && (
            <>
              <Separator className="mx-2 w-auto bg-sidebar-border" />
              <SidebarGroup>
                <SidebarGroupLabel className="flex items-center gap-1">
                  <ShieldCheck size={12} />
                  <span>Admin</span>
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    <SidebarMenuItem>
                      <SidebarMenuButton asChild isActive={isActive('/admin')}>
                        <Link href="/admin">
                          <ShieldCheck size={16} />
                          <span>Admin Panel</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </>
          )}
        </SidebarContent>

        <SidebarFooter className="border-t border-sidebar-border p-2">
          <div className="flex items-center gap-2 px-2 py-1 group-data-[collapsible=icon]:justify-center">
            <div className="w-7 h-7 rounded-full bg-purple-100 dark:bg-purple-900 flex items-center justify-center text-purple-700 dark:text-purple-300 text-xs font-bold flex-shrink-0">
              {user?.username?.[0]?.toUpperCase() ?? 'U'}
            </div>
            <div className="group-data-[collapsible=icon]:hidden min-w-0">
              <p className="text-xs font-medium text-sidebar-foreground truncate">{user?.first_name || user?.username || 'User'}</p>
              <p className="text-xs text-sidebar-foreground/50 truncate">@{user?.username}</p>
            </div>
          </div>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="flex h-12 items-center gap-2 border-b px-4 bg-background/95 backdrop-blur sticky top-0 z-10">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="h-4" />
          <span className="text-sm text-muted-foreground">
            {user ? `Logged in as @${user.username}` : 'Onichan Panel'}
          </span>
          {user?.is_premium && (
            <span className="ml-auto text-xs bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full font-medium">
              ⭐ Premium
            </span>
          )}
        </header>
        <main className="flex-1 p-6">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
