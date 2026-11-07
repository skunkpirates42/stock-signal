import "server-only";

export const API_BASE = process.env.FLASK_API_URL ?? "http://127.0.0.1:8000";
export const READ_TIMEOUT_MS = 10_000;
