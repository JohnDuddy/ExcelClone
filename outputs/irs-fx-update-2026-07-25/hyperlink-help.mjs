import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load(
  "C:\\Users\\drdud\\Downloads\\Brazilian Rental Properties.xlsx",
);
const workbook = await SpreadsheetFile.importXlsx(input);

const exact = workbook.help("range.hyperlink", {
  include: "index,examples,notes",
  maxChars: 6000,
});
console.log(exact.ndjson);

if (!exact.ndjson || exact.ndjson.includes("matched 0")) {
  const broad = workbook.help("*", {
    search: "hyperlink",
    include: "index,examples,notes",
    maxChars: 12000,
  });
  console.log(broad.ndjson);
}
