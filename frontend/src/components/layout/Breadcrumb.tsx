// src/components/layout/Breadcrumb.tsx
import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

interface BreadcrumbSegment {
  label: string;
  path: string;
}

function humanize(segment: string): string {
  return decodeURIComponent(segment)
    .replace(/-/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function buildSegments(pathname: string): BreadcrumbSegment[] {
  const parts = pathname.split("/").filter(Boolean);

  return parts.map((part, index) => ({
    label: humanize(part),
    path: `/${parts.slice(0, index + 1).join("/")}`,
  }));
}

/**
 * Displays the current navigation hierarchy, automatically derived from
 * the active route. Always begins with "Home"; the final segment
 * represents the current page and is rendered as plain text rather
 * than a link.
 */
interface BreadcrumbProps {
  repositoryName?: string;
  filePath?: string;
}

export function Breadcrumb({ repositoryName, filePath }: BreadcrumbProps) {
  const { pathname } = useLocation();
  const segments = repositoryName
    ? [
        { label: repositoryName, path: pathname },
        ...(filePath
          ? filePath.split("/").map((part, index, parts) => ({
              label: humanize(part),
              path: `${pathname}?file=${encodeURIComponent(parts.slice(0, index + 1).join("/"))}`,
            }))
          : []),
      ]
    : buildSegments(pathname);

  return (
    <nav aria-label="Breadcrumb" className="flex items-center">
      <ol className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <li className="flex items-center">
          {segments.length === 0 ? (
            <span className="font-medium text-foreground" aria-current="page">
              Home
            </span>
          ) : (
            <Link to="/" className="transition-colors hover:text-foreground font-medium">
              Home
            </Link>
          )}
        </li>

        {segments.map((segment, index) => {
          const isLast = index === segments.length - 1;

          return (
            <Fragment key={segment.path}>
              <li aria-hidden="true" className="flex items-center">
                <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
              </li>
              <li className="flex items-center">
                {isLast ? (
                  <span className="font-semibold text-foreground" aria-current="page">
                    {segment.label}
                  </span>
                ) : (
                  <Link to={segment.path} className="transition-colors hover:text-foreground font-medium">
                    {segment.label}
                  </Link>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
