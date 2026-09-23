// src/components/dashboard/ImportRepositoryDialog.tsx
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const importRepositorySchema = z.object({
  repositoryUrl: z
    .string()
    .min(1, "A repository URL is required.")
    .url("Enter a valid URL.")
    .regex(
      /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?\/?$/,
      "Enter a valid GitHub repository URL, e.g. https://github.com/owner/repo.",
    ),
});

export type ImportRepositoryFormValues = z.infer<typeof importRepositorySchema>;

interface ImportRepositoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: ImportRepositoryFormValues) => void | Promise<void>;
  isLoading?: boolean;
}

/**
 * Dialog for importing a GitHub repository by URL. Validates input
 * with Zod and delegates submission to the caller via `onSubmit`;
 * performs no API calls itself.
 */
export function ImportRepositoryDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: ImportRepositoryDialogProps) {
  const form = useForm<ImportRepositoryFormValues>({
    resolver: zodResolver(importRepositorySchema),
    defaultValues: { repositoryUrl: "" },
  });

  const handleSubmit = form.handleSubmit(async (values) => {
    await onSubmit(values);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Import Repository</DialogTitle>
          <DialogDescription>
            Enter the URL of a public or accessible GitHub repository to begin indexing it.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <FormField
              control={form.control}
              name="repositoryUrl"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>GitHub Repository URL</FormLabel>
                  <FormControl>
                    <Input placeholder="https://github.com/owner/repository" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Import Repository
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
