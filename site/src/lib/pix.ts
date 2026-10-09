// PIX "copia e cola" (BR Code): the Banco Central's EMV layout, with the
// CRC16-CCITT (0x1021, start 0xFFFF) of everything before it.

export function crc16(text: string): string {
  let crc = 0xffff;
  for (const byte of new TextEncoder().encode(text)) {
    crc ^= byte << 8;
    for (let i = 0; i < 8; i++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
  }
  return crc.toString(16).toUpperCase().padStart(4, "0");
}

/** Without accents or anything banks do not take, at most max characters. */
function plain(text: string, max: number): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\x20-\x7e]/g, "")
    .trim()
    .slice(0, max);
}

function field(id: string, value: string): string {
  return `${id}${String(value.length).padStart(2, "0")}${value}`;
}

export type Pix = { key: string; name: string; city: string; txid?: string };

export function pixPayload({ key, name, city, txid = "***" }: Pix): string {
  const account = field("00", "br.gov.bcb.pix") + field("01", key.trim());
  const body =
    field("00", "01") +
    field("26", account) +
    field("52", "0000") +
    field("53", "986") +
    field("58", "BR") +
    field("59", plain(name, 25)) +
    field("60", plain(city, 15)) +
    field("62", field("05", txid)) +
    "6304";
  return body + crc16(body);
}
