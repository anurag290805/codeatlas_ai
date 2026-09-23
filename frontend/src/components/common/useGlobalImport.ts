import { useContext } from "react";
import { ImportContext } from "@/components/common/ImportContext";

/**
 * Access the shell-level import dialog. Safe to call before the provider
 * mounts — falls back to a no-op so consumers never need to null-check.
 */
export function useGlobalImport(): { openImport: () => void } {
  const context = useContext(ImportContext);
  return context ?? { openImport: () => {} };
}