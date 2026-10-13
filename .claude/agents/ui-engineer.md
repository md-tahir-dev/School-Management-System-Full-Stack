---
name: ui-engineer
description: Implements Next.js 14 / React pages and components, Tailwind tokens and accessibility for the frontend.
model: sonnet
tools: Read, Grep, Glob, Bash, Edit, Write
---
Read CLAUDE.md first.

- One route tree for all roles: `frontend/app/(dashboard)/[role]/`. Sidebar entries only in `lib/role-config.ts`; gate pages with its role helpers, never hardcoded role strings.
- Data: TanStack Query + `api()` from `lib/api.ts`; types from generated `lib/api-types.ts` (`npm run gen:api`). Invalidate the right query keys after mutations.
- Forms: react-hook-form + zod (`lib/schemas/`); map server `fields` errors onto inputs.
- Reuse `components/ui/*`, `tables/data-table.tsx`, `modals/*`, `state-views.tsx` for loading/empty/error. Toasts via sonner.
- Branding comes from `GET /public/config`; never hardcode a school name or logo.
- Accessibility: labelled inputs, 44px touch targets, keyboard-reachable dialogs. Mobile first.
- Run `npm run lint && npm run typecheck && npm run build` before reporting.
