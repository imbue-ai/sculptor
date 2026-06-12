/**
 * Custom error class for validation errors from the API
 */
export class ValidationError extends Error {
  status = 422;
  detail: Array<{ loc: Array<string | number>; msg: string; type: string }>;

  constructor(detail: Array<{ loc: Array<string | number>; msg: string; type: string }>) {
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
