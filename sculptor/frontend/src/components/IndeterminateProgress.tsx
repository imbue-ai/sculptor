import type { ReactElement } from "react";

import styles from "./IndeterminateProgress.module.scss";

export type IndeterminateProgressSize = "1" | "2" | "3";

type IndeterminateProgressProps = {
  size?: IndeterminateProgressSize;
  className?: string;
};

const SIZE_CLASS_NAMES: Record<IndeterminateProgressSize, string> = {
  "1": styles.size1,
  "2": styles.size2,
  "3": styles.size3,
};

export const IndeterminateProgress = ({ size, className }: IndeterminateProgressProps): ReactElement => {
  const resolvedSize = size ?? "2";
  const classNames = [styles.root, SIZE_CLASS_NAMES[resolvedSize], className].filter(Boolean).join(" ");
  return <div role="progressbar" aria-busy="true" className={classNames} />;
};
