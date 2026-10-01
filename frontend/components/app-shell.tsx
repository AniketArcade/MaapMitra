"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import {
  Award,
  Building2,
  Clock3,
  FileText,
  Gauge,
  LayoutDashboard,
  LogOut,
  MapPin,
  ScrollText,
  ShieldCheck,
  User,
  UserCog,
  Users,
} from "lucide-react";

import { BrandLogo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/instruments", label: "Instruments", icon: Gauge },
  { href: "/applications", label: "Applications", icon: FileText },
  { href: "/profile", label: "Profile", icon: User },
];

// Spec 17 §6.8: SUPER_ADMIN gets a fuller flat sidebar instead of the single "Admin" link
// DISTRICT_ADMIN still keeps (spec 17 D1; spec 18 D1 keeps DISTRICT_ADMIN on it too, for now).
const SUPER_ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/applications", label: "Applications", icon: FileText },
  { href: "/instruments", label: "Instruments", icon: Gauge },
  { href: "/admin/certificates", label: "Certificates", icon: Award },
  { href: "/admin/certificates/expiring-soon", label: "Expiring soon", icon: Clock3 },
  { href: "/admin/gatc", label: "GATC directory", icon: Building2 },
  { href: "/admin/lmo", label: "LMO directory", icon: UserCog },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText },
  { href: "/profile", label: "Profile", icon: User },
];

// Spec 18 §6.17: STATE_ADMIN gets its own flat sidebar, one rank down from SUPER_ADMIN_NAV — no
// national-only items, plus a "Districts" link neither other admin nav has.
const STATE_ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/applications", label: "Applications", icon: FileText },
  { href: "/instruments", label: "Instruments", icon: Gauge },
  { href: "/admin/certificates", label: "Certificates", icon: Award },
  { href: "/admin/certificates/expiring-soon", label: "Expiring soon", icon: Clock3 },
  { href: "/admin/districts", label: "Districts", icon: MapPin },
  { href: "/admin/lmo", label: "LMO directory", icon: UserCog },
  { href: "/admin/gatc", label: "GATC directory", icon: Building2 },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText },
  { href: "/profile", label: "Profile", icon: User },
];

// UX guard only. The backend enforces every permission.
export function AppShell({ children }: { children: ReactNode }) {
  const { user, status, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated" || !user) {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Loading…
      </main>
    );
  }

  // UX guard only. The backend enforces every permission.
  const navItems =
    user.role === "SUPER_ADMIN"
      ? SUPER_ADMIN_NAV
      : user.role === "STATE_ADMIN"
        ? STATE_ADMIN_NAV
        : ADMIN_ROLES.includes(user.role)
          ? [...NAV, { href: "/admin", label: "Admin", icon: ShieldCheck }]
          : NAV;

  return (
    <SidebarProvider>
      <Sidebar collapsible="offcanvas">
        <SidebarHeader>
          <div className="px-2 py-1.5">
            <BrandLogo tone="dark" iconClassName="size-5" textClassName="text-sm" />
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarMenu>
            {navItems.map((item) => {
              const Icon = item.icon;
              // "/admin" (Dashboard) would otherwise prefix-match every /admin/* sub-route too.
              const isActive =
                item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton isActive={isActive} render={<Link href={item.href} />}>
                    <Icon className="size-4" aria-hidden="true" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarContent>
        <SidebarFooter>
          <div className="flex flex-col gap-2 px-2 py-1.5">
            <span className="truncate text-xs text-sidebar-foreground/70">{user.email}</span>
            <Button variant="outline" size="sm" onClick={() => void logout()}>
              <LogOut className="size-4" aria-hidden="true" />
              Log out
            </Button>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="flex items-center gap-2 border-b px-4 py-3 md:hidden">
          <SidebarTrigger />
          <BrandLogo iconClassName="size-5" textClassName="text-sm" />
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto"
            aria-label="Log out"
            onClick={() => void logout()}
          >
            <LogOut className="size-4" aria-hidden="true" />
          </Button>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
