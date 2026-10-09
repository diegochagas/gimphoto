import { describe, expect, it } from "vitest";
import { crc16, pixPayload } from "@/lib/pix";

describe("PIX copy-and-paste code", () => {
  it("matches the Banco Central's BR Code example byte for byte", () => {
    expect(pixPayload({ key: "123e4567-e12b-12d1-a456-426655440000", name: "Fulano de Tal", city: "BRASILIA" })).toBe(
      "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D",
    );
  });

  it("drops accents and cuts the name to 25 and the city to 15 characters", () => {
    const payload = pixPayload({ key: "a@b.co", name: "João Ação da Silva Pereira Santos", city: "São José dos Campos" });
    expect(payload).toContain("5925Joao Acao da Silva Perei");
    expect(payload).toContain("6015Sao Jose dos Ca");
  });

  it("ends with the CRC of everything before it", () => {
    const payload = pixPayload({ key: "+5511999999999", name: "Example", city: "Sao Paulo" });
    expect(payload.slice(-4)).toBe(crc16(payload.slice(0, -4)));
  });
});
