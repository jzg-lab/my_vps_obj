/** Only transport failures can leave a same-query snapshot visible. */
export function isTemporaryServiceReadFailure(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  if ("status" in error)
    return (
      typeof error.status === "number" &&
      Number.isInteger(error.status) &&
      (error.status === 429 || (error.status >= 500 && error.status < 600))
    );
  return (
    error instanceof TypeError ||
    (error instanceof Error &&
      (error.name === "TimeoutError" ||
        (error.name === "AbortError" && error.message === "request_cancelled")))
  );
}
