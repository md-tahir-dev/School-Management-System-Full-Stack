"use client";

import { useId, useMemo, useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Flat string form state keyed by API field path ("guardian.father_cnic"). The API is the validator:
 * blank strings become null server-side, and its `fields` errors land next to the matching input.
 */
export function useApiForm(initial: Record<string, string>) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Stable identities, so callers can list them as effect dependencies.
  const actions = useMemo(() => ({
    set: (name: string, value: string) => {
      setValues((p) => ({ ...p, [name]: value }));
      setErrors((p) => (p[name] ? { ...p, [name]: "" } : p));
    },
    reset: (next: Record<string, string>) => { setValues(next); setErrors({}); },
    /** Call from onError; returns true when field errors were shown. */
    showErrors: (e: unknown) => {
      const fields = e instanceof ApiError ? e.fields ?? {} : {};
      setErrors(fields);
      return Object.keys(fields).length > 0;
    },
  }), []);
  return {
    values,
    errors,
    ...actions,
    /** Values under `prefix.` as a nested object, e.g. pick("guardian") -> { father_name, ... }. */
    pick: (prefix: string) => Object.fromEntries(Object.entries(values).filter(([k]) => k.startsWith(`${prefix}.`)).map(([k, v]) => [k.slice(prefix.length + 1), v])),
  };
}
export type ApiForm = ReturnType<typeof useApiForm>;

function Shell({ id, label, error, hint, className, children }: { id: string; label: string; error?: string; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn("flex flex-col gap-1.5 text-sm", className)}>
      <label htmlFor={id} className="font-medium">{label}</label>
      {children}
      {error ? <span id={`${id}-d`} className="text-xs text-danger" role="alert">{error}</span> : hint ? <span id={`${id}-d`} className="text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

type TextProps = { form: ApiForm; name: string; label: string; hint?: string; className?: string } & Omit<InputHTMLAttributes<HTMLInputElement>, "form" | "name" | "value" | "onChange" | "className">;
export function TextField({ form, name, label, hint, className, ...rest }: TextProps) {
  const id = useId();
  return (
    <Shell id={id} label={label} error={form.errors[name]} hint={hint} className={className}>
      <Input id={id} aria-describedby={form.errors[name] || hint ? `${id}-d` : undefined} value={form.values[name] ?? ""} aria-invalid={!!form.errors[name]} onChange={(e) => form.set(name, e.target.value)} {...rest} />
    </Shell>
  );
}

type SelectProps = { form: ApiForm; name: string; label: string; options: (string | { value: string; label: string })[]; placeholder?: string; hint?: string; className?: string; onValue?: (v: string) => void } & Omit<SelectHTMLAttributes<HTMLSelectElement>, "form" | "name" | "value" | "onChange" | "className">;
export function SelectField({ form, name, label, options, placeholder, hint, className, onValue, ...rest }: SelectProps) {
  const id = useId();
  return (
    <Shell id={id} label={label} error={form.errors[name]} hint={hint} className={className}>
      <Select id={id} aria-describedby={form.errors[name] || hint ? `${id}-d` : undefined} value={form.values[name] ?? ""} aria-invalid={!!form.errors[name]} onChange={(e) => { form.set(name, e.target.value); onValue?.(e.target.value); }} {...rest}>
        <option value="">{placeholder ?? "Select..."}</option>
        {options.map((o) => (typeof o === "string" ? <option key={o} value={o}>{humanize(o)}</option> : <option key={o.value} value={o.value}>{o.label}</option>))}
      </Select>
    </Shell>
  );
}

/** "full_time" -> "Full time". */
export const humanize = (s: string) => (s.charAt(0).toUpperCase() + s.slice(1)).replace(/_/g, " ");

export function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-lg border border-border bg-card p-4 sm:p-5">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </fieldset>
  );
}
