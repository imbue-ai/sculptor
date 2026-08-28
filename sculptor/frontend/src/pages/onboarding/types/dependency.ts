type DependencyInstalled = {
  state: "installed";
  path: string;
  version: string;
  isOverride?: boolean;
};

type DependencyNotInstalled = {
  state: "not-installed";
};

type DependencyWrongVersion = {
  state: "wrong-version";
  path: string;
  version: string;
  requiredVersion: string;
  isOverride?: boolean;
};

type DependencyError = {
  state: "error";
  message: string;
};

type DependencyLoading = {
  state: "loading";
};

type DependencyInstalling = {
  state: "installing";
};

type DependencyNeedsAuth = {
  state: "needs-auth";
  path: string;
  version: string;
};

type DependencyAuthenticating = {
  state: "authenticating";
  path: string;
  version: string;
};

export type DependencyStatus =
  | DependencyInstalled
  | DependencyNotInstalled
  | DependencyWrongVersion
  | DependencyError
  | DependencyLoading
  | DependencyInstalling
  | DependencyNeedsAuth
  | DependencyAuthenticating;
