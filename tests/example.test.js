import { describe, expect, it } from "vitest";
import { TestDriver } from "testdriverai/vitest/hooks";

describe("Sample Web Suite", () => {
  it("should load the page and verify content", async (context) => {
    const testdriver = TestDriver(context);

    await testdriver.provision.chrome({ url: "https://example.com" });

    const assertResult = await testdriver.assert(
      "The page displays text stating this domain is for use in documentation examples without needing permission"
    );
    expect(assertResult).toBeTruthy();
  });
});
