import { createContext } from "react";

interface ImportContextValue {
  /** Opens the shared repository import dialog from anywhere in the shell. */
  openImport: () => void;
}

/**
 * Shell-level import dialog context. The consumer hook (`useGlobalImport`)
 * and the provider component (`ImportProvider`) live in separate modules so
 * each file fast-refreshes cleanly and never mixes hooks with components.
 */
export const ImportContext = createContext<ImportContextValue | null>(null);