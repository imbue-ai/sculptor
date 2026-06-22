import { setProjectAnnotations } from "@storybook/react";
import { beforeAll } from "vitest";
import * as projectAnnotations from "./preview";

// More info at: https://storybook.js.org/docs/api/portable-stories/portable-stories-vitest#setprojectannotations
const project = setProjectAnnotations([projectAnnotations]);

beforeAll(project.beforeAll);
