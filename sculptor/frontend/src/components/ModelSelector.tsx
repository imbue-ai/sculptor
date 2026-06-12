import { Flex, Select, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { LlmModel } from "~/api";
import { ElementIds } from "~/api";
import { getModelShortName } from "~/common/modelConstants.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";

import styles from "./ModelSelector.module.scss";

type ModelSelectorProps = {
  model: LlmModel;
  onModelChange: (model: LlmModel) => void;
};

export const ModelSelector = ({ model, onModelChange }: ModelSelectorProps): ReactElement => (
  <Select.Root size="1" value={model} onValueChange={onModelChange}>
    <Select.Trigger className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} variant="ghost">
      <Flex align="center">
        <Text size="1">{getModelShortName(model)}</Text>
      </Flex>
    </Select.Trigger>
    <Select.Content position="popper" sideOffset={5}>
      <Select.Group>
        <Select.Label>Model</Select.Label>
        <ModelSelectOptions optionTestId={ElementIds.MODEL_OPTION} />
      </Select.Group>
    </Select.Content>
  </Select.Root>
);
