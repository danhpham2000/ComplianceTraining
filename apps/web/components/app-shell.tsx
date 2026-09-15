"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  ChevronDown,
  GraduationCap,
  LayoutGrid,
  LogOut,
  PlayCircle,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { apiRequest } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";

type NavLink = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  matchPrefixes?: string[];
  exact?: boolean;
};

type RouteMeta = {
  title: string;
  subtitle: string;
};

const adminLinks: NavLink[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/training/new", label: "Build Training", icon: GraduationCap },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

const employeeLinks: NavLink[] = [
  { href: "/employee", label: "Dashboard", icon: LayoutGrid, matchPrefixes: ["/employee"], exact: true },
  { href: "/employee/training", label: "Training", icon: PlayCircle, matchPrefixes: ["/employee/training", "/learn"] },
  { href: "/settings", label: "Settings", icon: Settings2, matchPrefixes: ["/settings"] },
];

const publicRoutes = new Set(["/", "/login", "/register", "/verify-email"]);
const adminRoutePrefixes = ["/dashboard", "/training"];
const employeeRoutePrefixes = ["/employee", "/learn"];

const routeMeta: Record<string, RouteMeta> = {
  "/dashboard": {
    title: "Dashboard",
    subtitle: "Training activity, delivery status, and employee access",
  },
  "/training/new": {
    title: "Build Training",
    subtitle: "Create a training module from one approved source",
  },
  "/settings": {
    title: "Settings",
    subtitle: "Password, access, and role management",
  },
  "/employee": {
    title: "Dashboard",
    subtitle: "Assigned training, due dates, and completion flow",
  },
  "/employee/training": {
    title: "Training",
    subtitle: "Assigned modules, due dates, and completion status",
  },
};

function getHomeRoute(role: string | undefined) {
  return role === "EMPLOYEE" ? "/employee" : "/dashboard";
}

function getRouteMeta(pathname: string, role: string | undefined): RouteMeta {
  if (pathname.startsWith("/learn/")) {
    return {
      title: "Training Session",
      subtitle: "Watch, answer, and complete within policy",
    };
  }

  if (pathname.startsWith("/training/") && pathname !== "/training/new") {
    return {
      title: "Training Review",
      subtitle: "Source preview, publish controls, and final question approval",
    };
  }

  return routeMeta[pathname] ?? {
    title: role === "EMPLOYEE" ? "Workspace" : "Admin Workspace",
    subtitle: role === "EMPLOYEE" ? "Assigned learning and completion flow" : "Training operations and governance",
  };
}

function initials(value: string) {
  return value
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function UtilityButton({
  children,
  badge,
  active = false,
  onClick,
}: {
  children: ReactNode;
  badge?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative inline-flex size-11 items-center justify-center rounded-2xl border border-border bg-white text-muted-foreground shadow-sm transition-colors hover:bg-secondary/60 hover:text-foreground dark:bg-[#171f2b] dark:text-[#8fa1b8] dark:hover:bg-[#1f2937] dark:hover:text-[#edf2f8]",
        active && "border-primary/20 bg-[#fff5ea] text-primary dark:bg-[#2a1c10] dark:text-[#ffb25d]",
      )}
    >
      {children}
      {badge ? (
        <span className="absolute -right-1 -top-1 inline-flex min-w-5 items-center justify-center rounded-full bg-foreground px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {badge}
        </span>
      ) : null}
    </button>
  );
}

function notificationTime(value: string) {
  const date = new Date(value);
  const sameDay = new Date().toDateString() === date.toDateString();
  return sameDay
    ? new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(date)
    : shortDate(value);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { actor, ready, signOut } = useAuth();
  const isPublicRoute = publicRoutes.has(pathname);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ready || isPublicRoute || actor) {
      return;
    }
    router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [actor, isPublicRoute, pathname, ready, router]);

  useEffect(() => {
    if (!notificationsOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!notificationsRef.current) {
        return;
      }
      if (!notificationsRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [notificationsOpen]);

  useEffect(() => {
    if (!ready || !actor || isPublicRoute) {
      return;
    }

    const onAdminRoute = adminRoutePrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
    const onEmployeeRoute = employeeRoutePrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

    if (actor.role === "EMPLOYEE" && onAdminRoute) {
      router.replace("/employee");
      return;
    }

    if (actor.role !== "EMPLOYEE" && onEmployeeRoute) {
      router.replace("/dashboard");
    }
  }, [actor, isPublicRoute, pathname, ready, router]);

  const notifications = useQuery({
    queryKey: ["notifications", actor?.id ?? "guest"],
    queryFn: () => apiRequest<Notification[]>("/notifications"),
    enabled: Boolean(actor) && !isPublicRoute,
    refetchInterval: 15_000,
  });
  const unreadCount = useMemo(
    () => (notifications.data ?? []).filter((item) => !item.is_read).length,
    [notifications.data],
  );
  const markRead = useMutation({
    mutationFn: (notificationIds: string[]) =>
      apiRequest<{ message: string }>("/notifications/read", {
        method: "POST",
        body: { notification_ids: notificationIds },
      }),
    onSuccess: () => notifications.refetch(),
  });
  const markAllRead = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>("/notifications/read", {
        method: "POST",
        body: { mark_all: true },
      }),
    onSuccess: () => notifications.refetch(),
  });

  if (isPublicRoute) {
    if (pathname === "/") {
      return (
        <div className="min-h-screen px-4 py-5 md:px-6">
          <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-7xl items-center justify-center rounded-[2rem] border border-border/80 bg-white/92 p-4 shadow-[0_30px_90px_rgba(36,32,28,0.06)] dark:bg-[#141a24]/92 dark:shadow-[0_30px_90px_rgba(0,0,0,0.28)] md:p-6">
            <main className="flex w-full flex-1 items-center justify-center">{children}</main>
          </div>
        </div>
      );
    }

    return (
      <div className="min-h-screen px-4 py-5 md:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-7xl flex-col rounded-[2rem] border border-border/80 bg-white/92 p-4 shadow-[0_30px_90px_rgba(36,32,28,0.06)] dark:bg-[#141a24]/92 dark:shadow-[0_30px_90px_rgba(0,0,0,0.28)] md:p-6">
          <header className="flex items-center rounded-[1.7rem] border border-border/70 bg-white px-5 py-4 dark:bg-[#171d28]">
            <Link href="/" className="flex items-center gap-3">
              <div className="flex flex-col items-center rounded-[1.2rem] bg-white px-3 py-2 dark:bg-[#111722]">
                <Image
                  src="/nextphase-logo.png"
                  alt="NextPhase.ai"
                  width={190}
                  height={42}
                  priority
                  className="h-7 w-auto md:h-8"
                />
                <span className="mt-1 text-center text-[10px] font-medium tracking-[0.08em] text-[#8e775f]">
                  Compliance
                </span>
              </div>
            </Link>
          </header>
          <main className="flex-1">{children}</main>
        </div>
      </div>
    );
  }

  if (!ready || !actor) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#fbfbfd] dark:bg-[#0f141c]">
        <div className="space-y-3 text-center">
          <div className="mx-auto inline-flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <ShieldCheck className="size-5" />
          </div>
          <p className="text-sm font-medium text-foreground">Loading workspace</p>
          <p className="text-sm text-muted-foreground">Preparing your signed-in view.</p>
        </div>
      </div>
    );
  }

  const links = actor.role === "EMPLOYEE" ? employeeLinks : adminLinks;
  const homeRoute = getHomeRoute(actor.role);
  const currentMeta = getRouteMeta(pathname, actor.role);
  const displayName = actor.name ?? actor.email;
  const userInitials = initials(displayName || actor.email || "U");

  return (
    <div className="min-h-screen bg-[#fbfbfd] text-foreground dark:bg-[#0f141c]">
      <div className="flex min-h-screen flex-col md:grid md:grid-cols-[224px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-white dark:bg-[#121823] md:border-b-0 md:border-r">
          <div className="border-b border-border px-4 py-4">
            <Link href={homeRoute} className="inline-flex flex-col items-center">
              <Image
                src="/nextphase-logo.png"
                alt="NextPhase.ai"
                width={214}
                height={48}
                priority
                className="h-7 w-auto dark:brightness-[1.08]"
              />
              <span className="mt-1 text-center text-[10px] font-medium tracking-[0.08em] text-[#8e775f]">
                Compliance
              </span>
            </Link>
          </div>

          <div className="flex h-full flex-col px-2.5 py-5">
            <nav className="space-y-1.5">
              {links.map((link) => {
                const activePrefixes = link.matchPrefixes ?? [link.href];
                const active = link.exact
                  ? activePrefixes.some((prefix) => pathname === prefix)
                  : activePrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
                const Icon = link.icon;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={cn(
                      "flex items-center gap-3 rounded-[0.95rem] px-3.5 py-2.5 text-[13px] font-medium transition-colors",
                      active
                        ? "bg-[#fff4e8] text-primary shadow-[inset_0_0_0_1px_rgba(243,136,32,0.08)] dark:bg-[#2a1c10] dark:text-[#ffb25d] dark:shadow-[inset_0_0_0_1px_rgba(255,154,56,0.12)]"
                        : "text-[#6f819c] hover:bg-[#f7f9fc] hover:text-foreground dark:text-[#8fa1b8] dark:hover:bg-[#171f2b]",
                    )}
                  >
                    <Icon className={cn("size-4.5 shrink-0", active ? "text-primary dark:text-[#ffb25d]" : "text-[#7f90a8] dark:text-[#71839b]")} />
                    <span>{link.label}</span>
                    {active ? <span className="ml-auto text-primary dark:text-[#ffb25d]">›</span> : null}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto border-t border-border px-2 pt-4">
              <div className="flex items-center gap-3 rounded-[1rem] bg-[#fbfbfd] px-3 py-2.5 dark:bg-[#171f2b]">
                <div className="inline-flex size-10 items-center justify-center rounded-full bg-[#3d3a38] text-xs font-semibold text-white">
                  {userInitials}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-foreground">{displayName}</p>
                  <p className="truncate text-[12px] text-[#7b8ca5]">{actor.email}</p>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="border-b border-border bg-white dark:bg-[#121823]">
            <div className="flex min-h-16 items-center justify-between gap-4 px-5 md:px-6">
              <div className="min-w-0">
                <h1 className="truncate text-[1.35rem] font-semibold tracking-[-0.04em] text-foreground md:text-[1.45rem]">
                  {currentMeta.title}
                </h1>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden items-center gap-3 md:flex">
                  <div className="relative" ref={notificationsRef}>
                    <UtilityButton
                      badge={unreadCount ? `${Math.min(unreadCount, 9)}${unreadCount > 9 ? "+" : ""}` : undefined}
                      active={notificationsOpen}
                      onClick={() => setNotificationsOpen((value) => !value)}
                    >
                      <Bell className="size-4.5" />
                    </UtilityButton>

                    {notificationsOpen ? (
                      <div className="absolute right-0 top-14 z-30 w-[360px] overflow-hidden rounded-[1.6rem] border border-border bg-white shadow-[0_24px_90px_rgba(31,24,16,0.14)] dark:bg-[#171d28] dark:shadow-[0_24px_90px_rgba(0,0,0,0.34)]">
                        <div className="flex items-center justify-between border-b border-border px-5 py-4">
                          <div>
                            <p className="text-sm font-semibold text-foreground">Notifications</p>
                            <p className="text-xs text-[#7b8ca5]">
                              {unreadCount ? `${unreadCount} unread` : "All caught up"}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => markAllRead.mutate()}
                            className="text-xs font-medium text-primary"
                          >
                            Mark all read
                          </button>
                        </div>

                        <div className="max-h-[420px] overflow-y-auto p-3">
                          {(notifications.data ?? []).length ? (
                            <div className="space-y-2">
                              {(notifications.data ?? []).map((item) => (
                                <button
                                  key={item.id}
                                  type="button"
                                  onClick={() => {
                                    if (!item.is_read) {
                                      markRead.mutate([item.id]);
                                    }
                                    setNotificationsOpen(false);
                                    if (item.link_url) {
                                      router.push(item.link_url);
                                    }
                                  }}
                                  className={cn(
                                    "block w-full rounded-[1.2rem] border px-4 py-3 text-left transition-colors",
                                    item.is_read
                                      ? "border-border bg-white text-[#647791] hover:bg-[#f8fafc] dark:bg-[#141a24] dark:text-[#98a9bf] dark:hover:bg-[#1a2230]"
                                      : "border-primary/15 bg-[#fff8f1] text-foreground hover:bg-[#fff2e3] dark:bg-[#2a1c10] dark:text-[#edf2f8] dark:hover:bg-[#342213]",
                                  )}
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <p className="text-sm font-semibold">{item.title}</p>
                                      <p className="mt-1 text-sm leading-6">{item.body}</p>
                                    </div>
                                    {!item.is_read ? (
                                      <span className="mt-1 size-2.5 shrink-0 rounded-full bg-primary" />
                                    ) : null}
                                  </div>
                                  <p className="mt-2 text-xs text-[#92a1b5]">{notificationTime(item.created_at)}</p>
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="rounded-[1.2rem] border border-dashed border-border px-4 py-8 text-center text-sm text-[#7b8ca5]">
                              Assignment and completion activity will show up here.
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button type="button" className="flex items-center gap-2.5 rounded-full pl-2 pr-2.5">
                      <div className="inline-flex size-10 items-center justify-center rounded-full bg-[#3d3a38] text-xs font-semibold text-white">
                        {userInitials}
                      </div>
                      <div className="hidden min-w-0 md:block">
                        <p className="truncate text-[13px] font-medium text-[#6d7f98]">{displayName}</p>
                      </div>
                      <ChevronDown className="hidden size-4 text-[#93a2b7] md:block" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-52">
                    <DropdownMenuLabel>{displayName}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => router.push("/settings")}>
                      <Settings2 className="mr-2 size-4" />
                      Settings
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() => {
                        void signOut().then(() => router.replace("/login"));
                      }}
                    >
                      <LogOut className="mr-2 size-4" />
                      Sign out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </header>

          <main className="flex-1 px-5 py-5 md:px-6">
            <div className="mb-5 flex flex-col gap-2.5 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-[13px] text-[#7b8ca5]">{currentMeta.subtitle}</p>
              </div>

              {actor.role !== "EMPLOYEE" ? (
                <button
                  type="button"
                  onClick={() => router.push("/settings")}
                  className={cn(
                    buttonVariants({ variant: "outline", size: "sm" }),
                    "w-fit rounded-2xl border-[#dbe2ec] bg-white px-3.5 text-[13px] text-[#5b6f8c] shadow-none hover:bg-[#f7f9fc] dark:border-[#263243] dark:bg-[#171f2b] dark:text-[#c0cddd] dark:hover:bg-[#1f2937]",
                  )}
                >
                  <Settings2 className="size-4" />
                  Settings
                </button>
              ) : null}
            </div>

            <div className="min-w-0">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
