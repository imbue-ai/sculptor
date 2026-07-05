// A <Toast> driven by a Jotai atom: a non-null atom value opens the toast with that
// payload, and closing it (auto-dismiss, swipe, or the X) writes null back so the
// atom's owner can raise it again later. AppShell mounts one of these per app-level
// toast atom; everything variant-specific (type, an action button such as Retry)
// rides along in the payload, so one component covers both error and info toasts.

import type { WritableAtom } from "jotai";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback } from "react";

import { type ToastType } from "~/common/state/atoms/toasts.ts";
import { Toast } from "~/components/Toast.tsx";

// The payload contract the app-level toast atoms share (see ErrorToastData /
// InfoToastData in common/state/atoms/toasts.ts): a title plus optional
// description/variant/action. `action` admits null because the error atoms model
// "no action" as an explicit null.
export type AtomToastData = {
  title: string;
  description?: ReactNode;
  type?: ToastType;
  action?: { label: string; handleClick: () => void } | null;
};

// Writable so the toast can clear itself on close. Only null is ever written, which
// keeps atoms with narrower payload types (e.g. a required `action`) assignable.
export type AtomToastAtom = WritableAtom<AtomToastData | null, [null], void>;

type AtomToastProps = {
  toastAtom: AtomToastAtom;
  // Auto-dismiss delay; omitted, the Toast default applies.
  duration?: number;
};

const AtomToastComponent = ({ toastAtom, duration }: AtomToastProps): ReactElement => {
  const data = useAtomValue(toastAtom);
  const setData = useSetAtom(toastAtom);

  // Stable callback so the memoized <Toast> bails out instead of re-rendering on
  // every unrelated commit while it sits closed.
  const handleOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setData(null);
    },
    [setData],
  );

  return (
    <Toast
      open={data !== null}
      onOpenChange={handleOpenChange}
      title={data?.title}
      description={data?.description}
      type={data?.type}
      action={data?.action ?? undefined}
      duration={duration}
    />
  );
};

// Memoized because instances sit always-mounted (and usually closed) in the shell;
// with stable props (a module-level atom, a literal duration) only a payload change
// re-renders one.
export const AtomToast = memo(AtomToastComponent);
