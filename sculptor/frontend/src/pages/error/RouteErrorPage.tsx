import type { ReactElement } from "react";
import { useRouteError } from "react-router-dom";

import { ErrorPage } from "./ErrorPage.tsx";

export const RouteErrorPage = (): ReactElement => {
  const error = useRouteError();
  // TODO (PROD-2166): Verify we need to capture errors here
  return <ErrorPage error={error} isCapturingErrorWithSentry={true} />;
};
