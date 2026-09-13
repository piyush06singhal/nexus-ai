"use client";

/**
 * Re-export the shared dashboard primitives (StatCard, SectionCard, …) so the
 * Phase 12 centers use exactly the same components as Control Center and the
 * external/integrations surfaces.
 */
export {
  StatCard,
  SectionCard,
  Dash,
  ActionButton,
  StringList,
  JsonBlock,
  Row,
  DetailCard,
} from "@/app/(external)/_components/ui";