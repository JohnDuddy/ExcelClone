import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:\\Users\\drdud\\Downloads\\Brazilian Rental Properties.xlsx";
const outputDir = "C:\\dev\\ExcelClone\\outputs\\irs-fx-update-2026-07-25\\inspection";

await fs.mkdir(outputDir, { recursive: true });

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table,definedName,drawing",
  maxChars: 16000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 120,
});

const matches = await workbook.inspect({
  kind: "match",
  searchTerm: "exchange|rate|BRL|USD|real|dollar|tax|IRS|currency",
  options: { useRegex: true, maxResults: 250 },
  maxChars: 20000,
});

const formulas = await workbook.inspect({
  kind: "formula",
  options: { maxResults: 500 },
  maxChars: 30000,
});

await fs.writeFile(path.join(outputDir, "summary.ndjson"), summary.ndjson ?? String(summary), "utf8");
await fs.writeFile(path.join(outputDir, "matches.ndjson"), matches.ndjson ?? String(matches), "utf8");
await fs.writeFile(path.join(outputDir, "formulas.ndjson"), formulas.ndjson ?? String(formulas), "utf8");

const sheetInspection = [];
const sheets = workbook.worksheets.items;
for (const sheet of sheets) {
  const usedRange = sheet.getUsedRange();
  const usedAddress = usedRange?.address ?? null;
  const region = usedAddress
    ? await workbook.inspect({
        kind: "region",
        sheetId: sheet.name,
        range: usedAddress,
        maxChars: 20000,
        tableMaxRows: 120,
        tableMaxCols: 30,
        tableMaxCellChars: 160,
      })
    : null;

  sheetInspection.push({
    name: sheet.name,
    usedAddress,
    region: region?.ndjson ?? null,
  });

  if (usedAddress) {
    const preview = await workbook.render({
      sheetName: sheet.name,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    const safeName = sheet.name.replace(/[<>:"/\\|?*]/g, "_");
    await fs.writeFile(
      path.join(outputDir, `${safeName}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

await fs.writeFile(
  path.join(outputDir, "sheets.json"),
  JSON.stringify(sheetInspection, null, 2),
  "utf8",
);

console.log(JSON.stringify({
  sheets: sheetInspection.map(({ name, usedAddress }) => ({ name, usedAddress })),
  outputDir,
}, null, 2));
