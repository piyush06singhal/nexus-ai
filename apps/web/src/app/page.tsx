import { SystemStatus } from "@/components/dashboard/SystemStatus";
import { PlaceholderCard } from "@/components/dashboard/PlaceholderCard";
import { NAV_SECTIONS } from "@/lib/nav";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Operational overview of your NEXUS workforce. Foundation phase — most
          areas are placeholders.
        </p>
      </div>

      <SystemStatus />

      <section aria-label="Workforce overview">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Workforce
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {NAV_SECTIONS.map((section) => (
            <PlaceholderCard
              key={section.href}
              title={section.label}
              description={section.description}
            />
          ))}
        </div>
      </section>
    </div>
  );
}