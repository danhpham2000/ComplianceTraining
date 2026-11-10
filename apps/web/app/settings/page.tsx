"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Globe2, KeyRound, Trash2, UserPlus, Users2 } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { apiRequest } from "@/lib/api";
import { DirectoryUser, UserPreferences } from "@/lib/types";
import { cn } from "@/lib/utils";

const roleOptions = ["OWNER", "ADMIN", "MANAGER", "EMPLOYEE"] as const;
const inviteRoleOptions = ["ADMIN", "MANAGER", "EMPLOYEE"] as const;
const statusOptions = ["ACTIVE", "INACTIVE"] as const;
const adminSettingsSections = [
  { id: "general", label: "General", icon: Globe2 },
  { id: "people", label: "People", icon: Users2 },
  { id: "security", label: "Security", icon: KeyRound },
] as const;
const employeeSettingsSections = [
  { id: "general", label: "General", icon: Globe2 },
  { id: "security", label: "Security", icon: KeyRound },
] as const;

type SectionId = "general" | "people" | "security";

export default function SettingsPage() {
  const { actor, refresh } = useAuth();
  const { persona } = usePersona();
  const settingsSections = persona.role === "EMPLOYEE" ? employeeSettingsSections : adminSettingsSections;
  const [section, setSection] = useState<SectionId>("general");
  const directory = useQuery({
    queryKey: ["directory", persona.email],
    queryFn: () => apiRequest<DirectoryUser[]>("/auth/directory"),
    enabled: persona.role !== "EMPLOYEE",
  });
  const preferences = useQuery({
    queryKey: ["preferences", persona.email],
    queryFn: () => apiRequest<UserPreferences>("/auth/preferences"),
  });
  const members = useMemo(() => directory.data ?? [], [directory.data]);
  const [timeZoneDraft, setTimeZoneDraft] = useState("");
  const [timeZoneMessage, setTimeZoneMessage] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<(typeof inviteRoleOptions)[number]>("EMPLOYEE");
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const browserTimeZone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return "";
    }
  }, []);
  const timeZoneOptions = useMemo(() => {
    const zones = new Set<string>();
    try {
      const supported = Intl.supportedValuesOf?.("timeZone") ?? [];
      for (const zone of supported) {
        zones.add(zone);
      }
    } catch {
      // Ignore and rely on current values below.
    }
    for (const zone of [browserTimeZone, actor?.time_zone, preferences.data?.time_zone, timeZoneDraft]) {
      if (zone) {
        zones.add(zone);
      }
    }
    return [...zones].sort((left, right) => left.localeCompare(right));
  }, [actor?.time_zone, browserTimeZone, preferences.data?.time_zone, timeZoneDraft]);

  const changePassword = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>("/auth/change-password", {
        method: "POST",
        body: {
          current_password: currentPassword,
          new_password: newPassword,
        },
      }),
    onSuccess: (data) => {
      setPasswordMessage(data.message);
      setCurrentPassword("");
      setNewPassword("");
    },
  });
  const updateTimeZone = useMutation({
    mutationFn: (nextTimeZone: string) =>
      apiRequest<UserPreferences>("/auth/preferences", {
        method: "PATCH",
        body: {
          time_zone: nextTimeZone,
        },
      }),
    onSuccess: async (data) => {
      setTimeZoneDraft(data.time_zone ?? "");
      setTimeZoneMessage("Time zone updated.");
      await Promise.all([preferences.refetch(), refresh()]);
    },
  });
  const inviteMember = useMutation({
    mutationFn: () =>
      apiRequest<DirectoryUser>("/auth/invite", {
        method: "POST",
        body: {
          name: inviteName.trim() || undefined,
          email: inviteEmail.trim().toLowerCase(),
          role: inviteRole,
        },
      }),
    onSuccess: async (member) => {
      setInviteMessage(`Invitation sent to ${member.email}.`);
      setInviteName("");
      setInviteEmail("");
      setInviteRole("EMPLOYEE");
      setInviteOpen(false);
      await directory.refetch();
    },
  });
  const effectiveTimeZone = timeZoneDraft || preferences.data?.time_zone || actor?.time_zone || browserTimeZone;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: "easeOut" }}
      className="overflow-hidden rounded-[1.9rem] border border-border/80 bg-white shadow-[0_20px_60px_rgba(31,24,16,0.06)]"
    >
      <div className="grid min-h-[calc(100vh-13rem)] xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-[#fbfbfd] xl:border-b-0 xl:border-r">
          <div className="space-y-4 p-5">
            <div className="space-y-1">
              {settingsSections.map((item) => {
                const Icon = item.icon;
                const active = item.id === section;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSection(item.id)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-[1rem] px-3 py-3 text-left transition-colors",
                      active
                        ? "bg-[#f1f3f7] text-foreground shadow-[inset_0_0_0_1px_rgba(36,32,28,0.06)]"
                        : "text-[#5f728c] hover:bg-[#f7f9fc] hover:text-foreground",
                    )}
                  >
                    <Icon className={cn("size-4 shrink-0", active ? "text-primary" : "text-[#8391a4]")} />
                    <span className="text-sm font-medium">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <main className="min-w-0 bg-white">
          <div className="space-y-8 p-6 md:p-8 xl:p-10">
            {section === "general" ? (
              <>
                <div>
                  <h1 className="text-[2rem] font-semibold tracking-[-0.05em] text-foreground">General</h1>
                  <p className="mt-2 text-sm text-[#6f819c]">
                    Personal preferences for this account.
                  </p>
                </div>

                <Card className="rounded-[1.5rem] border-border/80 shadow-none">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-base">Time zone</CardTitle>
                    <CardDescription>
                      Auto-detected from your browser and used for date displays in the workspace.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-7 pt-1">
                    <Field label="Time zone">
                      <Select value={effectiveTimeZone} onValueChange={setTimeZoneDraft}>
                        <SelectTrigger className="h-11 rounded-2xl bg-white">
                          <SelectValue placeholder="Select a time zone" />
                        </SelectTrigger>
                        <SelectContent className="max-h-[22rem]">
                          {timeZoneOptions.map((zone) => (
                            <SelectItem key={zone} value={zone}>
                              {formatTimeZoneLabel(zone)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <div className="flex flex-wrap gap-4 pt-2">
                      <Button
                        type="button"
                        className="h-10 min-w-[132px] px-6"
                        disabled={updateTimeZone.isPending || !effectiveTimeZone}
                        onClick={() => updateTimeZone.mutate(effectiveTimeZone)}
                      >
                        {updateTimeZone.isPending ? <Spinner className="size-4" /> : null}
                        {updateTimeZone.isPending ? "Saving..." : "Save"}
                      </Button>
                    </div>
                    <div className="pt-1">
                      <div className="rounded-[1rem] border border-border bg-[#fcfcfe] px-4 py-3.5 text-sm text-muted-foreground">
                        Current saved time zone: {actor?.time_zone || "Not saved yet"}
                      </div>
                    </div>
                    {timeZoneMessage ? <p className="text-sm text-[#58725d]">{timeZoneMessage}</p> : null}
                    {updateTimeZone.error ? <p className="text-sm text-destructive">{updateTimeZone.error.message}</p> : null}
                  </CardContent>
                </Card>
              </>
            ) : null}

            {section === "people" ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h1 className="text-[2rem] font-semibold tracking-[-0.05em] text-foreground">People</h1>
                    <p className="mt-2 text-sm text-[#6f819c]">
                      Update role and access status for workspace members.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant={inviteOpen ? "outline" : "default"}
                    className="h-10 px-5"
                    onClick={() => {
                      setInviteMessage(null);
                      setInviteOpen((value) => !value);
                    }}
                  >
                    <UserPlus className="size-4" />
                    Invite member
                  </Button>
                </div>

                <Card className="rounded-[1.5rem] border-border/80 shadow-none">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Directory</CardTitle>
                    <CardDescription>Only the active workspace accounts that matter.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="hidden rounded-[1rem] border border-border bg-[#f8f9fc] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7b8ca5] md:grid md:grid-cols-[minmax(0,1.55fr)_140px_140px_180px]">
                      <span>Member</span>
                      <span>Role</span>
                      <span>Status</span>
                      <span>Actions</span>
                    </div>
                    {members.map((member) => (
                      <MemberRow
                        key={member.id}
                        currentUserId={actor?.id}
                        member={member}
                        onSaved={() => directory.refetch()}
                      />
                    ))}
                  </CardContent>
                </Card>
              </>
            ) : null}

            {section === "security" ? (
              <>
                <div>
                  <h1 className="text-[2rem] font-semibold tracking-[-0.05em] text-foreground">Security</h1>
                  <p className="mt-2 text-sm text-[#6f819c]">Password update for the current account.</p>
                </div>

                <Card className="rounded-[1.5rem] border-border/80 shadow-none">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Password</CardTitle>
                    <CardDescription>Use a password only you know and rotate it when access changes.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <Field label="Current password">
                      <Input
                        className="h-11"
                        type="password"
                        value={currentPassword}
                        onChange={(event) => setCurrentPassword(event.target.value)}
                        placeholder="Current password"
                      />
                    </Field>
                    <Field label="New password">
                      <Input
                        className="h-11"
                        type="password"
                        value={newPassword}
                        onChange={(event) => setNewPassword(event.target.value)}
                        placeholder="New password"
                      />
                    </Field>

                    <div className="flex justify-end">
                      <Button
                        type="button"
                        className="h-10 px-5"
                        disabled={changePassword.isPending || !currentPassword || !newPassword}
                        onClick={() => changePassword.mutate()}
                      >
                        {changePassword.isPending ? "Saving..." : "Save"}
                      </Button>
                    </div>

                    {passwordMessage ? <p className="text-sm text-[#58725d]">{passwordMessage}</p> : null}
                    {changePassword.error ? <p className="text-sm text-destructive">{changePassword.error.message}</p> : null}
                  </CardContent>
                </Card>
              </>
            ) : null}
          </div>
        </main>
      </div>

      {inviteOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[rgba(36,32,28,0.34)] p-4 backdrop-blur-sm">
          <Card className="w-full max-w-3xl rounded-[1.7rem] border-border/80 shadow-[0_28px_90px_rgba(31,24,16,0.16)]">
            <CardHeader className="pb-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle className="text-[1.15rem]">Invite member</CardTitle>
                  <CardDescription className="mt-1 text-sm text-[#7b8ca5]">
                    Send workspace access to any teammate with a @nextphase.ai email.
                  </CardDescription>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 px-5"
                  onClick={() => setInviteOpen(false)}
                >
                  Cancel
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Name">
                  <Input
                    className="h-11"
                    value={inviteName}
                    onChange={(event) => setInviteName(event.target.value)}
                    placeholder="Full name"
                  />
                </Field>
                <Field label="Email">
                  <Input
                    className="h-11"
                    type="email"
                    value={inviteEmail}
                    onChange={(event) => setInviteEmail(event.target.value)}
                    placeholder="name@nextphase.ai"
                  />
                </Field>
                <Field label="Role">
                  <Select value={inviteRole} onValueChange={(value: (typeof inviteRoleOptions)[number]) => setInviteRole(value)}>
                    <SelectTrigger className="h-11 rounded-2xl bg-white">
                      <SelectValue placeholder="Role" />
                    </SelectTrigger>
                    <SelectContent>
                      {inviteRoleOptions.map((option) => (
                        <SelectItem key={option} value={option}>
                          {formatRoleLabel(option)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border pt-4">
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 px-5"
                  onClick={() => setInviteOpen(false)}
                >
                  Close
                </Button>
                <Button
                  type="button"
                  className="h-10 px-5"
                  disabled={inviteMember.isPending || !inviteEmail.trim()}
                  onClick={() => {
                    setInviteMessage(null);
                    inviteMember.mutate();
                  }}
                >
                  {inviteMember.isPending ? <Spinner className="size-4" /> : <UserPlus className="size-4" />}
                  {inviteMember.isPending ? "Sending..." : "Send invite"}
                </Button>
              </div>

              {inviteMessage ? <p className="text-sm text-[#58725d]">{inviteMessage}</p> : null}
              {inviteMember.error ? <p className="text-sm text-destructive">{inviteMember.error.message}</p> : null}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </motion.div>
  );
}

function MemberRow({
  member,
  currentUserId,
  onSaved,
}: {
  member: DirectoryUser;
  currentUserId?: string;
  onSaved: () => void;
}) {
  const [role, setRole] = useState<DirectoryUser["role"]>(member.role);
  const [status, setStatus] = useState<DirectoryUser["status"]>(member.status);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const dirty = role !== member.role || status !== member.status;
  const isCurrentUser = currentUserId === member.id;

  const mutation = useMutation({
    mutationFn: () =>
      apiRequest<DirectoryUser>(`/auth/directory/${member.id}`, {
        method: "PATCH",
        body: { role, status },
      }),
    onSuccess: (data) => {
      setRole(data.role);
      setStatus(data.status);
      onSaved();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>(`/auth/directory/${member.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      setDeleteOpen(false);
      onSaved();
    },
  });

  return (
    <>
      <div className="grid gap-3 rounded-[1.1rem] border border-border bg-white px-4 py-4 md:grid-cols-[minmax(0,1.55fr)_140px_140px_180px] md:items-center">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{member.name ?? member.email}</p>
          <p className="mt-1 truncate text-sm text-muted-foreground">{member.email}</p>
        </div>

        <Select value={role} onValueChange={(value: DirectoryUser["role"]) => setRole(value)}>
          <SelectTrigger className="h-10 rounded-2xl bg-white">
            <SelectValue placeholder="Role" />
          </SelectTrigger>
          <SelectContent>
            {roleOptions.map((option) => (
              <SelectItem key={option} value={option}>
                {formatRoleLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={status} onValueChange={(value: DirectoryUser["status"]) => setStatus(value)}>
          <SelectTrigger className="h-10 rounded-2xl bg-white">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map((option) => (
              <SelectItem key={option} value={option}>
                {formatStatusLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={dirty ? "default" : "outline"}
            className="h-10 px-4"
            disabled={mutation.isPending || !dirty || deleteMutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <Spinner className="size-4" /> : null}
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-10 px-3 text-destructive hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive"
            disabled={isCurrentUser || mutation.isPending || deleteMutation.isPending}
            title={isCurrentUser ? "You cannot remove your own account." : "Remove member"}
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="size-4" />
            <span className="sr-only">Remove member</span>
          </Button>
        </div>

        {mutation.error ? <p className="text-sm text-destructive md:col-span-4">{mutation.error.message}</p> : null}
        {deleteMutation.error ? <p className="text-sm text-destructive md:col-span-4">{deleteMutation.error.message}</p> : null}
      </div>

      <ConfirmationDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Remove member?"
        description={`Remove ${member.name ?? member.email} from this workspace. They will lose access immediately, but existing completion history remains available for records.`}
        confirmLabel="Remove member"
        isPending={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
      />
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {children}
    </label>
  );
}

function formatTimeZoneLabel(zone: string) {
  return zone.replaceAll("_", " / ").replaceAll("/", " / ");
}

function formatRoleLabel(role: string) {
  return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
}

function formatStatusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}
