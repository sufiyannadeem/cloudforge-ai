import { appConfig } from "@/lib/config";
import type { ApiError } from "@/types/api";

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly details?: unknown;

  constructor(
    message: string,
    status: number,
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.details = details;
  }
}

const createTimeoutSignal = (): AbortSignal => {
  return AbortSignal.timeout(appConfig.requestTimeoutMs);
};

const parseResponseBody = async (
  response: Response,
): Promise<unknown> => {
  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    return null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
};

const extractErrorMessage = (
  body: unknown,
  status: number,
): string => {
  if (
    typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string"
  ) {
    return body.message;
  }

  return `API request failed with status ${status}`;
};

export async function apiRequest<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(url, {
      ...options,
      signal: options.signal ?? createTimeoutSignal(),
      headers: {
        Accept: "application/json",
        ...(options.body
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers,
      },
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiClientError(
        "The request timed out. Please try again.",
        408,
      );
    }

    throw new ApiClientError(
      "Unable to connect to the backend service.",
      503,
      error,
    );
  }

  const body = await parseResponseBody(response);

  if (!response.ok) {
    const errorPayload: ApiError = {
      message: extractErrorMessage(body, response.status),
      details: body,
    };

    throw new ApiClientError(
      errorPayload.message,
      response.status,
      errorPayload.details,
    );
  }

  return body as T;
}

export async function apiGet<T>(url: string): Promise<T> {
  return apiRequest<T>(url, {
    method: "GET",
  });
}

export async function apiPost<T>(
  url: string,
  payload?: unknown,
): Promise<T> {
  return apiRequest<T>(url, {
    method: "POST",
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
}

export async function apiPatch<T>(
  url: string,
  payload: unknown,
): Promise<T> {
  return apiRequest<T>(url, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function apiDelete<T = void>(
  url: string,
): Promise<T> {
  return apiRequest<T>(url, {
    method: "DELETE",
  });
}
