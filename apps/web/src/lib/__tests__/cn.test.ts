import { describe, it, expect } from "vitest";
import { cn } from "@/lib/cn";

describe("cn", () => {
  it("merges class names", () => {
    const result = cn("text-red-500", "text-blue-500");
    expect(result).toBe("text-blue-500");
  });

  it("handles conditional classes", () => {
    const result = cn("base", false && "hidden", "extra");
    expect(result).toContain("base");
    expect(result).toContain("extra");
    expect(result).not.toContain("hidden");
  });

  it("deduplicates Tailwind classes", () => {
    const result = cn("p-2 p-4");
    expect(result).toBe("p-4");
  });

  it("returns empty string for no input", () => {
    expect(cn()).toBe("");
  });

  it("handles undefined and null gracefully", () => {
    const result = cn("base", undefined, null);
    expect(result).toBe("base");
  });
});
