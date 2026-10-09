import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Donate from "@/components/Donate";

type Config = NonNullable<Parameters<typeof Donate>[0]["config"]>;

const none: Config = { pix: { key: "", name: "", city: "" }, links: { kofi: "" }, goal: { monthly: 0, raised: 0, currency: "BRL" } };
const some: Config = {
  // the Banco Central's BR Code example key; the links are placeholders
  pix: { key: "123e4567-e12b-12d1-a456-426655440000", name: "Fulano de Tal", city: "BRASILIA" },
  links: { "github-sponsors": "https://github.com/sponsors/example", kofi: "", paypal: "https://www.paypal.com/donate/?hosted_button_id=EXAMPLE" },
  goal: { monthly: 500, raised: 125, currency: "BRL" },
};

async function render(lang: "en" | "pt", config: Config) {
  return renderToStaticMarkup(await Donate({ lang, config }));
}

describe("the donation section", () => {
  it("says donations open soon when no method is set up", async () => {
    const html = await render("en", none);
    expect(html).toContain("data-soon");
    expect(html).not.toContain("data-methods");
    expect(html).not.toContain("data-goal");
  });

  it("shows PIX with its code and QR, the set-up links only, and the goal", async () => {
    const html = await render("pt", some);
    expect(html).toContain("63041D3D");
    expect(html).toContain('alt="PIX QR code"');
    expect(html).toContain("data:image/svg+xml");
    expect(html).toContain('href="https://github.com/sponsors/example"');
    expect(html).toContain("PayPal");
    expect(html).not.toContain("Ko-fi");
    expect(html).toMatch(/R\$\s?125 de R\$\s?500/);
    expect(html).toContain("width:25%");
  });
});
