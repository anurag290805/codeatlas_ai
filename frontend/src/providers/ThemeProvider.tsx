import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { PropsWithChildren } from "react";

/**
 * Encapsulates next-themes configuration for the application, enabling
 * light/dark/system theme support via a `class` attribute on the
 * document root for Tailwind's dark mode variant and shadcn/ui.
 */
function ThemeProvider({ children }: PropsWithChildren) {
  if (typeof window !== "undefined") {
    const savedTheme = window.localStorage.getItem("theme");
    if (savedTheme && !["light", "dark", "system"].includes(savedTheme)) {
      document.documentElement.classList.remove(savedTheme);
      document.documentElement.classList.remove("light", "dark");
      document.documentElement.classList.add(
        window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      );
      window.localStorage.setItem("theme", "system");
    }
  }

  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      themes={["light", "dark", "system"]}
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}

export default ThemeProvider;
