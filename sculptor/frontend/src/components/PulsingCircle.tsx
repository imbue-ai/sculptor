import { Flex } from "@radix-ui/themes";
import type { PropsWithChildren, ReactElement } from "react";
import { forwardRef } from "react";

type PulsingCircleProps = {
  className?: string;
  size?: string | number;
};

const FlexSvg = forwardRef<HTMLDivElement, PropsWithChildren<PulsingCircleProps>>((props, ref): ReactElement => {
  const size = props.size ?? "16px";
  return (
    <Flex ref={ref}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        xmlns="http://www.w3.org/2000/svg"
        className={props.className}
      >
        {props.children}
      </svg>
    </Flex>
  );
});

export const BlandCircle = (props: PulsingCircleProps): ReactElement => {
  const innerColorVal = "var(--inner-color, var(--gray-8))";

  return (
    <FlexSvg {...props}>
      <circle cx="50%" cy="50%" r="35%" fill={innerColorVal} />
    </FlexSvg>
  );
};

export const PulsingCircle = forwardRef<HTMLDivElement, PulsingCircleProps>((props, ref): ReactElement => {
  const outerColorVal = "var(--outer-color, var(--accent-a4))";
  const innerColorVal = "var(--inner-color, var(--accent-8))";

  return (
    <FlexSvg {...props} ref={ref}>
      <circle cx="50%" cy="50%" r="25%" fill={outerColorVal}>
        <animate attributeName="r" values="40%;48%;40%" dur="2.0s" repeatCount="indefinite" />
      </circle>
      <circle cx="50%" cy="50%" r="25%" fill={innerColorVal} />
    </FlexSvg>
  );
});
