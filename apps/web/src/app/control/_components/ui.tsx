"use client";

/**
 * Re-export the shared dashboard primitives (StatCard, SectionCard, …) so the
 * Control Center pages use exactly the same components as /integrations.
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
} from "../../(external)/_components/ui";