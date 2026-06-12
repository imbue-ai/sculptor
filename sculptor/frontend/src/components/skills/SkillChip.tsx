import classnames from "classnames";
import { FileText } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import type { SkillEntry } from "~/common/state/hooks/useSkills";
import { TooltipIconButton } from "~/components/TooltipIconButton";

import styles from "./SkillChip.module.scss";

type SkillChipProps = {
  skill: SkillEntry;
  onClick: () => void;
  onMouseEnter?: (event: React.MouseEvent<HTMLDivElement>) => void;
  onMouseLeave?: () => void;
  onOpenInSculptor?: () => void;
  disabled?: boolean;
  /** Visually-highlighted "this row is the keyboard target" state. Mirrors
   * the hover styling so a search user can see what Enter will insert. */
  selected?: boolean;
};

export const SkillChip = ({
  skill,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onOpenInSculptor,
  disabled = false,
  selected = false,
}: SkillChipProps): ReactElement => {
  const handleClick = (): void => {
    if (!disabled) {
      onClick();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (disabled) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      className={classnames(styles.row, { [styles.disabled]: disabled, [styles.selected]: selected })}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-selected={selected || undefined}
      data-testid={ElementIds.SKILL_CHIP}
      data-skill-name={skill.name}
      data-selected={selected ? "true" : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <span className={styles.slash}>/</span>
      <span className={styles.name}>{skill.name}</span>

      {onOpenInSculptor !== undefined && (
        <span className={styles.actions}>
          <TooltipIconButton
            tooltipText="Open in Sculptor"
            aria-label="Open in Sculptor"
            className={styles.actionButton}
            onClick={(e): void => {
              e.stopPropagation();
              onOpenInSculptor();
            }}
          >
            <FileText size={14} />
          </TooltipIconButton>
        </span>
      )}
    </div>
  );
};
