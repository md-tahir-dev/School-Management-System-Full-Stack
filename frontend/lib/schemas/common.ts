import { z } from "zod";

/** Pakistani CNIC, formatted 00000-0000000-0. Used by the student and teacher forms in Phase 2. */
export const cnicSchema = z.string().regex(/^\d{5}-\d{7}-\d$/, "Use the format 00000-0000000-0");

export const optionalCnic = z.union([cnicSchema, z.literal("")]);
