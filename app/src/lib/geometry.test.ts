import { describe, expect, it } from "vitest";
import { bounds, polygonPoints } from "./geometry";

describe("geometry", () => {
  const box: [number, number][] = [[10, 20], [110.04, 22], [109, 52.26], [9, 50]];
  it("polygonPoints", () => expect(polygonPoints(box)).toBe("10,20 110,22 109,52.3 9,50"));
  it("bounds", () => expect(bounds(box)).toEqual({ x: 9, y: 20, width: 101.04, height: 32.26 }));
});
