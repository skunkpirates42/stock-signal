export class ResponseShapeError extends Error {
  override name = "ResponseShapeError";
  constructor(
    readonly path: string,
    readonly expected: string,
  ) {
    super(`${path}: expected ${expected}`);
  }
}

export type Read<T> = (value: unknown, path: string) => T;

export const readString: Read<string> = (value, path) => {
  if (typeof value !== "string") throw new ResponseShapeError(path, "string");
  return value;
};

export const readNumber: Read<number> = (value, path) => {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new ResponseShapeError(path, "finite number");
  return value;
};

export const readBoolean: Read<boolean> = (value, path) => {
  if (typeof value !== "boolean") throw new ResponseShapeError(path, "boolean");
  return value;
};

export function readLiteral<const T extends string | number>(...options: T[]): Read<T> {
  return (value, path) => {
    if (!options.includes(value as T)) throw new ResponseShapeError(path, options.join(" | "));
    return value as T;
  };
}

export function readNullable<T>(read: Read<T>): Read<T | null> {
  return (value, path) => (value === null ? null : read(value, path));
}

export function readOptional<T>(read: Read<T>): Read<T | undefined> {
  return (value, path) => (value === undefined ? undefined : read(value, path));
}

export function readArrayOf<T>(read: Read<T>): Read<T[]> {
  return (value, path) => {
    if (!Array.isArray(value)) throw new ResponseShapeError(path, "array");
    return value.map((item, index) => read(item, `${path}[${index}]`));
  };
}

function readPlainObject(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new ResponseShapeError(path, "object");
  return value as Record<string, unknown>;
}

export function readRecordOf<T>(read: Read<T>): Read<Record<string, T>> {
  return (value, path) =>
    Object.fromEntries(
      Object.entries(readPlainObject(value, path)).map(([key, item]) => [
        key,
        read(item, `${path}.${key}`),
      ]),
    );
}

export function readFields(value: unknown, path: string) {
  const record = readPlainObject(value, path);
  return <T>(key: string, read: Read<T>): T => read(record[key], `${path}.${key}`);
}
