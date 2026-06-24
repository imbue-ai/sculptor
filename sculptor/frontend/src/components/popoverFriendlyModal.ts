import type { Popover } from "@radix-ui/themes";
import type { ComponentProps } from "react";

// A host popover with a "popover-friendly modal" mounted inside it shouldn't
// dismiss when the user interacts with the modal. The modal tags its outer
// element with this attribute; popovers spread `popoverFriendlyModalGuard`
// onto their `Popover.Content` to honor the signal.
export const POPOVER_FRIENDLY_MODAL_ATTRIBUTE = "data-popover-friendly-modal";

const isInsidePopoverFriendlyModal = (target: EventTarget | null): boolean => {
  if (!(target instanceof Element)) return false;
  return target.closest(`[${POPOVER_FRIENDLY_MODAL_ATTRIBUTE}="true"]`) !== null;
};

type PopoverContentProps = ComponentProps<typeof Popover.Content>;

// Spread onto a `<Popover.Content>` to keep the popover open while any
// popover-friendly modal is interacting with it. Outside-interactions whose
// target lives inside such a modal are suppressed; everything else
// dismisses the popover as usual.
export const popoverFriendlyModalGuard: Pick<PopoverContentProps, "onInteractOutside"> = {
  onInteractOutside: (event): void => {
    if (isInsidePopoverFriendlyModal(event.target)) event.preventDefault();
  },
};
