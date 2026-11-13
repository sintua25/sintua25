import type { Point } from "../api/types";

export function polygonPoints(box: Point[]): string {
  return box.map(([x, y]) => `${round(x)},${round(y)}`).join(" ");
}

export function bounds(box: Point[]) {
  const xs = box.map((p) => p[0]);
  const ys = box.map((p) => p[1]);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}
