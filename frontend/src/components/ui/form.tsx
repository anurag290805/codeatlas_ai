import * as React from "react";
import {
  Controller,
  FormProvider,
  useFormContext,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";

import { cn } from "@/lib/utils";

const Form = FormProvider;

type FormFieldContextValue<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  name: TName;
};

const FormFieldContext = React.createContext<FormFieldContextValue<FieldValues, FieldPath<FieldValues>> | null>(null);
const FormItemContext = React.createContext<{ id: string } | null>(null);

function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>(props: ControllerProps<TFieldValues, TName>) {
  return (
    <FormFieldContext.Provider value={{ name: props.name as FieldPath<FieldValues> }}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

const FormItem = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <FormItemContext.Provider value={{ id: React.useId() }}>
      <div ref={ref} className={cn("space-y-2", className)} {...props} />
    </FormItemContext.Provider>
  ),
);
FormItem.displayName = "FormItem";

function useFormField() {
  const fieldContext = React.useContext(FormFieldContext);
  const itemContext = React.useContext(FormItemContext);
  const formContext = useFormContext();

  if (!fieldContext || !itemContext) {
    throw new Error("Form controls must be rendered inside FormField and FormItem.");
  }

  const fieldState = formContext.getFieldState(fieldContext.name, formContext.formState);
  const messageId = `${itemContext.id}-message`;

  return {
    id: itemContext.id,
    name: fieldContext.name,
    error: fieldState.error,
    formMessageId: messageId,
  };
}

const FormLabel = React.forwardRef<HTMLLabelElement, React.ComponentProps<"label">>(
  ({ className, ...props }, ref) => (
    <label ref={ref} className={cn("text-sm font-medium", className)} {...props} />
  ),
);
FormLabel.displayName = "FormLabel";

function FormControl({ children }: { children: React.ReactElement<Record<string, unknown>> }) {
  const { id, error, formMessageId } = useFormField();

  return React.cloneElement(children, {
    id,
    "aria-invalid": Boolean(error),
    "aria-describedby": error ? formMessageId : undefined,
  });
}

function FormMessage({ className, ...props }: React.ComponentProps<"p">) {
  const { error, formMessageId } = useFormField();

  if (!error?.message) return null;

  return (
    <p id={formMessageId} className={cn("text-sm text-destructive", className)} {...props}>
      {String(error.message)}
    </p>
  );
}

export { Form, FormControl, FormField, FormItem, FormLabel, FormMessage };
