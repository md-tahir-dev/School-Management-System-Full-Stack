"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, GraduationCap } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toaster";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isRole } from "@/lib/role-config";
import { loginSchema, type LoginValues } from "@/lib/schemas/auth";
import type { PublicConfig } from "@/lib/types";

/** Only allow same-site paths as post-login destinations (no open redirect). */
function safeNext(next: string | null, role: string) {
  if (next && next.startsWith(`/${role}`) && !next.startsWith("//")) return next;
  return `/${role}`;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { login, user, status } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: config } = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api<PublicConfig>("/public/config", { auth: false }),
    staleTime: 5 * 60_000,
  });

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { username: "", password: "" } });

  // Already signed in (e.g. opened /login in a second tab): go to the dashboard.
  useEffect(() => {
    if (status === "authenticated" && user && isRole(user.role)) {
      router.replace(user.must_change_password ? "/change-password" : safeNext(params.get("next"), user.role));
    }
  }, [status, user, router, params]);

  async function onSubmit(values: LoginValues) {
    setFormError(null);
    try {
      const signedIn = await login(values.username, values.password);
      toast.success(`Welcome back${signedIn.full_name ? `, ${signedIn.full_name.split(" ")[0]}` : ""}`);
      router.replace(signedIn.must_change_password ? "/change-password" : safeNext(params.get("next"), signedIn.role));
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "We couldn't reach the server. Check your connection and try again.");
    }
  }

  const schoolName = config?.school_name ?? "School Management System";

  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)]">
      {/* exercise-book panel */}
      <section className="ruled-paper relative flex flex-col justify-between bg-primary px-8 py-10 text-primary-foreground sm:px-14 lg:min-h-screen lg:py-14 lg:pl-28">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
            <GraduationCap className="h-5 w-5" aria-hidden />
          </span>
          <span className="font-semibold">School portal</span>
        </div>
        <div className="py-10 lg:py-0">
          <h1 className="max-w-xl text-4xl font-extrabold leading-[1.15] sm:text-5xl">{schoolName}</h1>
          {config?.slogan ? <p className="mt-4 max-w-md text-lg text-blue-100">{config.slogan}</p> : null}
        </div>
        <p className="hidden max-w-sm text-sm text-blue-100/90 lg:block">
          Attendance, results, fees and announcements, in one place for staff, students and families.
        </p>
      </section>

      <section className="flex items-center justify-center bg-card px-6 py-12 sm:px-12">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold">Sign in</h2>
          <p className="mt-1 text-sm text-muted-foreground">Use the username the school office gave you.</p>

          <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-5" noValidate>
            {formError && (
              <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
                {formError}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                autoCapitalize="none"
                autoFocus
                aria-invalid={!!errors.username}
                aria-describedby={errors.username ? "username-error" : undefined}
                {...register("username")}
              />
              {errors.username && (
                <p id="username-error" className="text-sm text-danger">
                  {errors.username.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="pr-11"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-2 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="text-sm text-danger">
                  {errors.password.message}
                </p>
              )}
            </div>
            <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
              Sign in
            </Button>
          </form>

          {config?.demo_accounts && (
            <div className="mt-8 rounded-lg border border-dashed border-border bg-muted p-4">
              <p className="text-sm font-semibold">Demo accounts</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Tap one to fill the form.</p>
              <ul className="mt-3 grid grid-cols-2 gap-2">
                {config.demo_accounts.map((a) => (
                  <li key={a.username}>
                    <button
                      type="button"
                      onClick={() => {
                        setValue("username", a.username ?? "");
                        setValue("password", a.password ?? "");
                      }}
                      className="w-full rounded-md border border-border bg-card px-3 py-2 text-left text-sm hover:border-primary"
                    >
                      <span className="block font-medium capitalize">{a.role}</span>
                      <span className="block text-xs text-muted-foreground">{a.username}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
