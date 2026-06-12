import { Link } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ErrorPage } from "./ErrorPage.tsx";

export const NotFoundErrorPage = (): ReactElement => {
  return (
    <ErrorPage
      isCapturingErrorWithSentry={false}
      headerText={
        <>
          The page you are looking for does not exist. Return to the{" "}
          <Link href="/" underline="always">
            home page
          </Link>
          .
        </>
      }
    />
  );
};
