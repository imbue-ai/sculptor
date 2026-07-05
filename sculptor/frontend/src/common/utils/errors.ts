type ValidationErrorDetail = {
  loc: Array<string | number>;
  msg: string;
  type: string;
};

/**
 * Custom error class for validation errors from the API
 */
export class ValidationError extends Error {
  status: number;
  detail: Array<ValidationErrorDetail>;

  constructor(detail: Array<ValidationErrorDetail>) {
    super("Validation Error");
    this.name = "ValidationError";
    this.status = 422;
    this.detail = detail;
  }
}

export class RequestTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RequestTimeoutError";
  }
}

/**
 * Custom error class for HTTP exceptions from the API
 */
export class HTTPException extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "HTTPException";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Extract a human-readable message from an unknown error, falling back to a default.
 */
export const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof HTTPException) {
    return error.detail;
  }

  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
};
