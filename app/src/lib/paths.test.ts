import { describe, expect, it } from "vitest";
import { baseName, dirName, joinPath } from "./paths";

describe("joinPath", () => {
  it("Windows", () => expect(joinPath("C:\\Klien\\Kas Maret\\", "sub/a.jpg")).toBe("C:\\Klien\\Kas Maret\\sub\\a.jpg"));
  it("POSIX", () => expect(joinPath("/data/klien", "sub/a.jpg")).toBe("/data/klien/sub/a.jpg"));
  it("akar", () => expect(joinPath("/data/klien/", "a.jpg")).toBe("/data/klien/a.jpg"));
});

describe("baseName/dirName", () => {
  it("bersarang", () => {
    expect(baseName("sub/dalam/a.jpg")).toBe("a.jpg");
    expect(dirName("sub/dalam/a.jpg")).toBe("sub/dalam");
  });
  it("di akar", () => {
    expect(baseName("a.jpg")).toBe("a.jpg");
    expect(dirName("a.jpg")).toBe("");
  });
});
