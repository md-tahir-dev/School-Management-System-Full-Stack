"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { changePasswordSchema, type ChangePasswordValues } from "@/lib/schemas/auth";

export default function ChangePasswordPage() {
  const router = useRouter();
  const { user, status, changePassword, logout } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const forced = user?.must_change_password ?? false;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({ resolver: zodResolver(changePasswordSchema) });

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  async function onSubmit(values: ChangePasswordValues) {
    setFormError(null);
    try {
      const updated = await changePassword(values.current_password, values.new_password);
      toast.success("Password changed. Your other devices were signed out.");
      router.replace(`/${updated.role}`);
    } catch (err) {
      if (err instanceof ApiError && Array.isArray(err.details) && err.details.length > 0) {
        setFormError(`${err.message} Your password ${err.details.join(", ")}.`);
      } else {
        setFormError(err instanceof ApiError ? err.message : "We couldn't reach the server. Please try again.");
      }
    }
  }

  const field = (id: keyof ChangePasswordValues, label: string, autoComplete: string, hint?: string) => (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="password"
        autoComplete={autoComplete}
        aria-invalid={!!errors[id]}
        aria-describedby={errors[id] ? `${id}-error` : hint ? `${id}-hint` : undefined}
        {...register(id)}
      />
      {errors[id] ? (
        <p id={`${id}-error`} className="text-sm text-danger">
          {errors[id]?.message}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md p-6 sm:p-8">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-100 text-primary">
          <KeyRound className="h-5 w-5" aria-hidden />
        </span>
        <h1 className="mt-4 text-xl font-bold">{forced ? "Set a new password" : "Change password"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {forced
            ? "You're using a temporary password. Choose your own to continue."
            : "Changing it signs you out of your other devices."}
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          {formError && (
            <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
              {formError}
            </div>
          )}
          {field("current_password", forced ? "Temporary password" : "Current password", "current-password")}
          {field("new_password", "New password", "new-password", "At least 8 characters, with a letter and a digit.")}
          {field("confirm_password", "Repeat new password", "new-password")}
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            {forced ? (
              <Button
                type="button"
                variant="ghost"
                onClick={async () => {
                  await logout();
                  router.replace("/login");
                }}
              >
                Sign out
              </Button>
            ) : (
              <Button type="button" variant="outline" onClick={() => router.back()}>
                Cancel
              </Button>
            )}
            <Button type="submit" loading={isSubmitting} disabled={status !== "authenticated"}>
              Update password
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}
