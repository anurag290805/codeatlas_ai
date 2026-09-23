import { useCallback, useMemo, useState, type ReactNode } from "react";
import { ImportRepositoryDialog } from "@/components/dashboard/ImportRepositoryDialog";
import { useImportRepository, useRepositories } from "@/hooks/useRepositories";
import { ImportContext } from "@/components/common/ImportContext";

/**
 * Hosts a single, shared repository-import dialog for the application
 * shell so any navigation affordance can trigger an import without
 * duplicating the mutation wiring on every page. Page-level import
 * dialogs (Dashboard, Repositories) remain independent.
 */
export function ImportProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const importRepository = useImportRepository();
  const repositoriesQuery = useRepositories();

  const openImport = useCallback(() => setOpen(true), []);

  const handleSubmit = useCallback(
    async (values: { repositoryUrl: string }) => {
      await importRepository.mutateAsync({ url: values.repositoryUrl });
      setOpen(false);
      void repositoriesQuery.refetch();
    },
    [importRepository, repositoriesQuery],
  );

  const value = useMemo(() => ({ openImport }), [openImport]);

  return (
    <ImportContext.Provider value={value}>
      {children}
      <ImportRepositoryDialog
        open={open}
        onOpenChange={setOpen}
        onSubmit={handleSubmit}
        isLoading={importRepository.isPending}
      />
    </ImportContext.Provider>
  );
}