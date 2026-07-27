import fs from "node:fs/promises";
import path from "node:path";
import JSZip from "jszip";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:\\Users\\drdud\\Downloads\\Brazilian Rental Properties.xlsx";
const outputDir = "C:\\dev\\ExcelClone\\outputs\\irs-fx-update-2026-07-25";
const outputPath = path.join(
  outputDir,
  "Brazilian Rental Properties - IRS FX Updated 2026-07-25.xlsx",
);
const dailyCsvPath = path.join(outputDir, "fred-dexbzus-daily.csv");
const hyperlinkMapPath = path.join(outputDir, "original-hyperlinks.json");
const asOfText = "2026-07-25 15:39 ET";

const IRS_GUIDANCE =
  "https://www.irs.gov/individuals/international-taxpayers/foreign-currency-and-currency-exchange-rates";
const IRS_YEARLY =
  "https://www.irs.gov/individuals/international-taxpayers/yearly-average-currency-exchange-rates";
const FED_DAILY = "https://fred.stlouisfed.org/series/DEXBZUS";
const TREASURY_DATA =
  "https://fiscaldata.treasury.gov/datasets/treasury-reporting-rates-exchange/";
const FINCEN_FBAR = "https://www.fincen.gov/reporting-maximum-account-value";

const monthly2025 = [
  6.0109, 5.7638, 5.7581, 5.7905, 5.6664, 5.5458,
  5.5332, 5.4455, 5.3630, 5.3832, 5.3415, 5.4557,
];
const monthly2026 = [
  5.3316, 5.1988, 5.2296, 5.0339, 4.9815, 5.1241, 5.13035,
  null, null, null, null, null,
];

const csvText = await fs.readFile(dailyCsvPath, "utf8");
const originalHyperlinks = JSON.parse(
  (await fs.readFile(hyperlinkMapPath, "utf8")).replace(/^\uFEFF/, ""),
);
const dailyRows = csvText
  .trim()
  .split(/\r?\n/)
  .slice(1)
  .map((line) => {
    const [date, rawRate] = line.split(",");
    return { date, rate: rawRate === "" ? null : Number(rawRate) };
  })
  .filter(({ rate }) => Number.isFinite(rate));

const latestDaily = dailyRows.at(-1);
const dailyStartRow = 5;
const dailyEndRow = dailyStartRow + dailyRows.length - 1;

await fs.mkdir(outputDir, { recursive: true });

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const rates2025 = workbook.worksheets.getItem("Rates 2025");
const rates2026 = workbook.worksheets.getItem("Rates 2026");

rates2025.getRange("C5:C16").values = monthly2025.map((value) => [value]);
rates2025.getRange("D5:D16").formulas = monthly2025.map((_, index) => [
  `=IF(C${index + 5}="","",1/C${index + 5})`,
]);
rates2025.getRange("A17").values = [["IRS Yearly Average"]];
rates2025.getRange("C17").values = [[5.593]];
rates2025.getRange("D17").formulas = [["=1/C17"]];
rates2025.getRange("A2").values = [[
  "Source: Federal Reserve H.10 monthly averages (BRL per USD). IRS 2025 yearly average is used for annual-only totals.",
]];
rates2025.getRange("A20").values = [[
  "• Government rates are source snapshots. Black values are formulas.",
]];
rates2025.getRange("A21").values = [[
  "• Transaction rule: use the prevailing spot rate when received, paid, or accrued. Monthly averages are used only where the workbook records a month but no exact date.",
]];
rates2025.getRange("A22").values = [[
  `• IRS 2025 yearly average: 5.593 BRL/USD. ${IRS_YEARLY}`,
]];
rates2025.getRange("A23").values = [[
  `• Federal Reserve H.10 / DEXBZUS monthly averages: ${FED_DAILY}`,
]];
rates2025.getRange("A24").values = [[
  `• FBAR 2025 uses the Treasury 12/31/2025 rate of 5.477. ${TREASURY_DATA}`,
]];

rates2026.getRange("C5:C16").values = monthly2026.map((value) => [value]);
rates2026.getRange("D5:D16").formulas = monthly2026.map((_, index) => [
  `=IF(C${index + 5}="","",1/C${index + 5})`,
]);
rates2026.getRange("A17").values = [["YTD Avg (provisional)"]];
rates2026.getRange("C17").formulas = [["=IFERROR(AVERAGE(C5:C16),\"\")"]];
rates2026.getRange("D17").formulas = [["=IF(C17=\"\",\"\",1/C17)"]];
rates2026.getRange("A2").values = [[
  "Source: Federal Reserve H.10 monthly averages. Jan-Jun are final; Jul is month-to-date through 07/17/2026; Aug-Dec are pending.",
]];
rates2026.getRange("A20").values = [[
  "• Government rates are source snapshots. Black values are formulas.",
]];
rates2026.getRange("A21").values = [[
  "• The IRS has not published a 2026 yearly average. C17 is a provisional YTD estimate and must not be treated as the final filing rate.",
]];
rates2026.getRange("A22").values = [[
  "• Use an exact transaction-date spot rate when the receipt/payment date is known. Future months remain blank.",
]];
rates2026.getRange("A24").values = [["AUTHORITATIVE EXCHANGE-RATE SOURCES:"]];
rates2026.getRange("A25:B28").values = [
  ["• IRS transaction-rate guidance:", IRS_GUIDANCE],
  ["• Federal Reserve H.10 / DEXBZUS:", FED_DAILY],
  ["• Treasury Reporting Rates (FBAR):", TREASURY_DATA],
  ["• FinCEN FBAR conversion instructions:", FINCEN_FBAR],
];

const fxDaily = workbook.worksheets.getOrAdd("FX Daily");
fxDaily.showGridLines = false;
fxDaily.getRange("A1:D1").merge();
fxDaily.getRange("A1").values = [["FEDERAL RESERVE H.10 DAILY BRL/USD RATES"]];
fxDaily.getRange("A2:D2").merge();
fxDaily.getRange("A2").values = [[
  `Snapshot refreshed ${asOfText}. Daily observations available through ${latestDaily.date}.`,
]];
fxDaily.getRange("A3:D3").values = [[
  "Latest observation",
  new Date(`${latestDaily.date}T12:00:00Z`),
  latestDaily.rate,
  "BRL per 1 USD",
]];
fxDaily.getRange("A4:D4").values = [[
  "Date",
  "BRL per 1 USD",
  "1 BRL in USD",
  "Source / status",
]];
fxDaily.getRange(`A${dailyStartRow}:B${dailyEndRow}`).values = dailyRows.map(
  ({ date, rate }) => [new Date(`${date}T12:00:00Z`), rate],
);
fxDaily.getRange(`C${dailyStartRow}`).formulas = [[`=1/B${dailyStartRow}`]];
fxDaily.getRange(`C${dailyStartRow}:C${dailyEndRow}`).fillDown();
fxDaily.getRange(`D${dailyStartRow}:D${dailyEndRow}`).values =
  dailyRows.map(() => ["Federal Reserve H.10"]);
fxDaily.getRange(`A${dailyStartRow}:A${dailyEndRow}`).format.numberFormat = "yyyy-mm-dd";
fxDaily.getRange("B3").format.numberFormat = "yyyy-mm-dd";
fxDaily.getRange(`B${dailyStartRow}:C${dailyEndRow}`).format.numberFormat = "0.000000";
fxDaily.getRange("C3").format.numberFormat = "0.000000";
fxDaily.getRange("A1:D1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 14 },
};
fxDaily.getRange("A2:D2").format = {
  fill: "#D9EAF7",
  font: { italic: true, color: "#44546A" },
  wrapText: true,
};
fxDaily.getRange("A4:D4").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};
fxDaily.getRange(`A4:D${dailyEndRow}`).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
fxDaily.getRange("A:A").format.columnWidth = 14;
fxDaily.getRange("B:C").format.columnWidth = 16;
fxDaily.getRange("D:D").format.columnWidth = 24;
fxDaily.freezePanes.freezeRows(4);

const fxAudit = workbook.worksheets.getOrAdd("FX Sources & Audit");
fxAudit.showGridLines = false;
fxAudit.getRange("A1:F1").merge();
fxAudit.getRange("A1").values = [["IRS / TREASURY FX METHOD AND SOURCE AUDIT"]];
fxAudit.getRange("A2:F2").merge();
fxAudit.getRange("A2").values = [[
  `As of ${asOfText}. Rates are BRL per 1 USD; divide BRL by the rate to obtain USD.`,
]];
fxAudit.getRange("A4:F4").values = [[
  "Use case",
  "Workbook method",
  "Rate",
  "Effective / as-of",
  "Status",
  "Authoritative source",
]];
fxAudit.getRange("A5:F11").values = [
  [
    "Dated income, expenses, and taxes",
    "Prevailing spot rate; FTC uses Date Paid when supplied",
    null,
    "Transaction date",
    "IRS method",
    IRS_GUIDANCE,
  ],
  [
    "Recurring monthly rent",
    "Federal Reserve H.10 monthly average when exact date is absent",
    null,
    "Monthly",
    "Consistent government source",
    FED_DAILY,
  ],
  [
    "2025 annual-only totals",
    "IRS published yearly average",
    5.593,
    "2025",
    "FINAL",
    IRS_YEARLY,
  ],
  [
    "2026 annual-only totals",
    "Federal Reserve H.10 YTD monthly average",
    null,
    "Through 2026-07-17",
    "PROVISIONAL",
    FED_DAILY,
  ],
  [
    "FBAR 2025",
    "Treasury year-end rate applied to every annual maximum",
    5.477,
    "2025-12-31",
    "FINAL",
    TREASURY_DATA,
  ],
  [
    "FBAR 2026",
    "Treasury 12/31/2026 rate",
    null,
    "Not yet available",
    "PENDING",
    TREASURY_DATA,
  ],
  [
    "Latest Federal Reserve spot",
    "Most recent published H.10 observation",
    latestDaily.rate,
    latestDaily.date,
    "CURRENT SNAPSHOT",
    FED_DAILY,
  ],
];
fxAudit.getRange("C8").formulas = [["='Rates 2026'!C17"]];
fxAudit.getRange("A13:E13").values = [[
  "Property basis audit",
  "Acquisition date",
  "Fed spot rate",
  "Workbook issue",
  "Review status",
]];
fxAudit.getRange("A14:E16").values = [
  ["Property 1", new Date("2025-06-13T12:00:00Z"), null, "Original model converts depreciation at annual average", "CPA REVIEW"],
  ["Property 2", new Date("2025-10-07T12:00:00Z"), null, "Original model converts depreciation at annual average", "CPA REVIEW"],
  ["Property 3", new Date("2026-04-17T12:00:00Z"), null, "Acquisition date conflicts with the 2025 property block", "DATA REVIEW"],
];
for (let row = 14; row <= 16; row += 1) {
  fxAudit.getRange(`C${row}`).formulas = [[
    `=VLOOKUP(B${row},'FX Daily'!$A$${dailyStartRow}:$B$${dailyEndRow},2,TRUE)`,
  ]];
}
fxAudit.getRange("A18:F18").merge();
fxAudit.getRange("A18").values = [[
  "Important: the IRS states that it has no single official exchange rate and generally accepts a consistently used posted rate. This workbook uses the government sources above and leaves unavailable future rates blank.",
]];
fxAudit.getRange("A19:F19").merge();
fxAudit.getRange("A19").values = [[
  "Tax-basis warning: acquisition and improvement costs may require transaction-date translation. The workbook's original annual-average depreciation conversion was not automatically changed; confirm basis, placed-in-service dates, and depreciation with a qualified tax professional.",
]];
fxAudit.getRange("A1:F1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 14 },
};
fxAudit.getRange("A2:F2").format = {
  fill: "#D9EAF7",
  font: { italic: true, color: "#44546A" },
};
for (const header of ["A4:F4", "A13:E13"]) {
  fxAudit.getRange(header).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
}
fxAudit.getRange("A5:F11").format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
fxAudit.getRange("C5:C16").format.numberFormat = "0.000000";
fxAudit.getRange("B14:B16").format.numberFormat = "yyyy-mm-dd";
fxAudit.getRange("C7").format.fill = "#E2F0D9";
fxAudit.getRange("C8").format.fill = "#FFF2CC";
fxAudit.getRange("C9").format.fill = "#E2F0D9";
fxAudit.getRange("C10").format.fill = "#FFF2CC";
fxAudit.getRange("E5:E16").format.font = { bold: true };
fxAudit.getRange("A18:F19").format = {
  fill: "#FFF2CC",
  font: { color: "#7F6000" },
  wrapText: true,
};
fxAudit.getRange("A:A").format.columnWidth = 27;
fxAudit.getRange("B:B").format.columnWidth = 43;
fxAudit.getRange("C:C").format.columnWidth = 15;
fxAudit.getRange("D:D").format.columnWidth = 20;
fxAudit.getRange("E:E").format.columnWidth = 20;
fxAudit.getRange("F:F").format.columnWidth = 55;
fxAudit.getRange("A1:F19").format.wrapText = true;
fxAudit.getRange("A18:F19").format.rowHeight = 40;
fxAudit.freezePanes.freezeRows(4);

const index = workbook.worksheets.getItem("INDEX");
index.getRange("A3").values = [[
  "Last Updated: July 25, 2026 (government FX data through July 17, 2026)",
]];
index.getRange("A19:B19").values = [[
  "FX Sources & Audit",
  "IRS method, authoritative rates, data freshness, and warnings",
]];
index.getRange("A21:B24").values = [
  ["IRS Yearly Average Rates", IRS_YEARLY],
  ["IRS Transaction-Rate Guidance", IRS_GUIDANCE],
  ["Federal Reserve H.10 / DEXBZUS", FED_DAILY],
  ["Treasury Reporting Rates (FBAR)", TREASURY_DATA],
];

const propertySheets = ["Property 1", "Property 2", "Property 3"];
for (const sheetName of propertySheets) {
  const sheet = workbook.worksheets.getItem(sheetName);
  for (let row = 18; row <= 29; row += 1) {
    sheet.getRange(`C${row}`).formulas = [[`='Rates 2025'!C${row - 13}`]];
    sheet.getRange(`D${row}`).formulas = [[
      `=IF(OR(B${row}="",C${row}<=0),"",B${row}/C${row})`,
    ]];
    sheet.getRange(`J${row}`).formulas = [[
      `=IF('Rates 2026'!C${row - 13}="","",'Rates 2026'!C${row - 13})`,
    ]];
    sheet.getRange(`K${row}`).formulas = [[
      `=IF(OR(I${row}="",J${row}<=0),"",I${row}/J${row})`,
    ]];
    sheet.getRange(`R${row}`).formulas = [[
      `=IF(OR(P${row}="",Q${row}<=0),"",P${row}/Q${row})`,
    ]];
  }
  for (let row = 34; row <= 43; row += 1) {
    sheet.getRange(`C${row}`).formulas = [["='Rates 2025'!C17"]];
    sheet.getRange(`D${row}`).formulas = [[
      `=IF(OR(B${row}="",C${row}<=0),"",B${row}/C${row})`,
    ]];
    sheet.getRange(`J${row}`).formulas = [["='Rates 2026'!C17"]];
    sheet.getRange(`K${row}`).formulas = [[
      `=IF(OR(I${row}="",J${row}<=0),"",I${row}/J${row})`,
    ]];
    sheet.getRange(`R${row}`).formulas = [[
      `=IF(OR(P${row}="",Q${row}<=0),"",P${row}/Q${row})`,
    ]];
  }
  sheet.getRange("B50").formulas = [[
    "=IF(OR(B49=\"\",'Rates 2025'!C17<=0),\"\",B49/'Rates 2025'!C17)",
  ]];
  sheet.getRange("I50").formulas = [[
    "=IF(OR(I49=\"\",'Rates 2026'!C17<=0),\"\",I49/'Rates 2026'!C17)",
  ]];
  sheet.getRange("P50").formulas = [["=IF(P49=\"\",\"\",\"\")"]];
  sheet.getRange("B51").formulas = [["=IF(B50=\"\",B48,B48-B50)"]];
  sheet.getRange("I51").formulas = [["=IF(I50=\"\",I48,I48-I50)"]];
  sheet.getRange("P51").formulas = [["=IF(P50=\"\",P48,P48-P50)"]];
}

const fbar2025 = workbook.worksheets.getItem("FBAR 2025");
for (let row = 15; row <= 26; row += 1) {
  fbar2025.getRange(`E${row}`).formulas = [["='FX Sources & Audit'!C9"]];
  fbar2025.getRange(`F${row}`).formulas = [[
    `=IF(OR(B${row}="",E${row}<=0),0,B${row}/E${row})`,
  ]];
  fbar2025.getRange(`G${row}`).formulas = [[
    `=IF(OR(C${row}="",E${row}<=0),0,C${row}/E${row})`,
  ]];
  fbar2025.getRange(`H${row}`).formulas = [[`=F${row}+G${row}`]];
  fbar2025.getRange(`I${row}`).formulas = [[
    `=IF(H${row}>10000,"⚠ YES - FILE FBAR","No")`,
  ]];
}
fbar2025.getRange("A34").values = [[
  "• FBAR conversion corrected: all maximum balances use Treasury's 12/31/2025 rate of 5.477 BRL/USD",
]];

const fbar2026 = workbook.worksheets.getItem("FBAR 2026");
for (let row = 15; row <= 26; row += 1) {
  fbar2026.getRange(`E${row}`).formulas = [[
    "=IF('FX Sources & Audit'!C10=\"\",\"\",'FX Sources & Audit'!C10)",
  ]];
  fbar2026.getRange(`F${row}`).formulas = [[
    `=IF(OR(B${row}="",E${row}<=0),"",B${row}/E${row})`,
  ]];
  fbar2026.getRange(`G${row}`).formulas = [[
    `=IF(OR(C${row}="",E${row}<=0),"",C${row}/E${row})`,
  ]];
  fbar2026.getRange(`H${row}`).formulas = [[
    `=IF(E${row}<=0,"",IFERROR(F${row},0)+IFERROR(G${row},0))`,
  ]];
  fbar2026.getRange(`I${row}`).formulas = [[
    `=IF(AND(B${row}="",C${row}=""),"No balances entered",IF(E${row}<=0,"Pending 12/31 rate",IF(H${row}>10000,"⚠ YES - FILE FBAR","No")))`,
  ]];
}
fbar2026.getRange("F27").formulas = [["=IF(COUNTA(B15:B26)=0,\"\",MAX(F15:F26))"]];
fbar2026.getRange("G27").formulas = [["=IF(COUNTA(C15:C26)=0,\"\",MAX(G15:G26))"]];
fbar2026.getRange("H27").formulas = [[
  "=IF(COUNTA(B15:C26)=0,\"\",IF('FX Sources & Audit'!C10=\"\",\"\",MAX(H15:H26)))",
]];
fbar2026.getRange("I27").formulas = [[
  "=IF(COUNTA(B15:C26)=0,\"No balances entered\",IF('FX Sources & Audit'!C10=\"\",\"Pending 12/31 Treasury rate\",IF(H27>10000,\"⚠ FBAR REQUIRED\",\"No FBAR Required\")))",
]];
fbar2026.getRange("A34").values = [[
  "• 2026 FBAR USD values remain pending until Treasury publishes the 12/31/2026 rate",
]];

for (const year of [2025, 2026]) {
  const sheet = workbook.worksheets.getItem(`FTC ${year}`);
  sheet.getRange("D4").values = [["Rate (date / avg)"]];
  for (let row = 5; row <= 15; row += 1) {
    const fallback = year === 2025 ? "'Rates 2025'!$C$17" : "'Rates 2026'!$C$17";
    sheet.getRange(`D${row}`).formulas = [[
      `=IF(F${row}="",${fallback},IF(OR(F${row}<'FX Daily'!$A$${dailyStartRow},F${row}>'FX Daily'!$A$${dailyEndRow}),"",VLOOKUP(F${row},'FX Daily'!$A$${dailyStartRow}:$B$${dailyEndRow},2,TRUE)))`,
    ]];
    sheet.getRange(`E${row}`).formulas = [[
      `=IF(OR(C${row}="",D${row}<=0),"",C${row}/D${row})`,
    ]];
  }
  sheet.getRange("A23:F23").merge();
  sheet.getRange("A23").values = [[
    "• Enter Date Paid to use the preceding available Federal Reserve H.10 spot rate; if blank, the IRS 2025 yearly average or provisional 2026 YTD average is used.",
  ]];
  sheet.getRange("A23:F23").format = {
    fill: "#FFF2CC",
    font: { italic: true, color: "#7F6000" },
    wrapText: true,
  };
  sheet.getRange("A23:F23").format.rowHeight = 34;
  sheet.getRange("C5:C16").format.numberFormat = "#,##0.00;[Red](#,##0.00);-";
  sheet.getRange("D5:D15").format.numberFormat = "0.000000";
  sheet.getRange("E5:E16").format.numberFormat = "$#,##0.00;[Red]($#,##0.00);-";
  sheet.getRange("D:D").format.columnWidth = 18;
  sheet.getRange("E:E").format.columnWidth = 15;
  sheet.getRange("F:F").format.columnWidth = 13;
}

function escapeFormulaString(value) {
  return String(value).replaceAll('"', '""');
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function decodeXml(value) {
  return value
    .replaceAll("&quot;", '"')
    .replaceAll("&apos;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function encodeXml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function getXmlAttribute(tag, name) {
  const match = tag.match(new RegExp(`\\b${escapeRegex(name)}="([^"]*)"`));
  return match ? decodeXml(match[1]) : null;
}

async function repairHyperlinkCachedValues(workbookPath, links) {
  const bytes = await fs.readFile(workbookPath);
  const zip = await JSZip.loadAsync(bytes);
  const workbookXml = await zip.file("xl/workbook.xml").async("string");
  const workbookRelsXml = await zip.file("xl/_rels/workbook.xml.rels").async("string");

  const relationshipTargets = new Map();
  for (const match of workbookRelsXml.matchAll(/<(?:\w+:)?Relationship\b[^>]*\/?>/g)) {
    const id = getXmlAttribute(match[0], "Id");
    const target = getXmlAttribute(match[0], "Target");
    if (id && target) relationshipTargets.set(id, target);
  }

  const sheetPaths = new Map();
  for (const match of workbookXml.matchAll(/<(?:\w+:)?sheet\b[^>]*\/?>/g)) {
    const name = getXmlAttribute(match[0], "name");
    const relId = getXmlAttribute(match[0], "r:id");
    const target = relationshipTargets.get(relId);
    if (!name || !target) continue;
    const normalized = target.replaceAll("\\", "/").replace(/^\//, "");
    sheetPaths.set(name, normalized.startsWith("xl/") ? normalized : `xl/${normalized}`);
  }

  let repairedCount = 0;
  for (const [sheetName, sheetLinks] of Object.entries(
    Object.groupBy(links, ({ sheet }) => sheet),
  )) {
    const sheetPath = sheetPaths.get(sheetName);
    const sheetFile = zip.file(sheetPath);
    if (!sheetFile) throw new Error(`Worksheet XML not found for ${sheetName}`);
    let sheetXml = await sheetFile.async("string");

    for (const link of sheetLinks) {
      const cellRef = escapeRegex(link.cell);
      const cellPattern = new RegExp(
        `<((?:\\w+:)?c)\\b([^>]*\\br="${cellRef}"[^>]*)>[\\s\\S]*?<\\/\\1>`,
      );
      const cellMatch = sheetXml.match(cellPattern);
      if (!cellMatch) throw new Error(`Hyperlink cell not found: ${sheetName}!${link.cell}`);

      const decodedCell = decodeXml(cellMatch[0]);
      const formulaMatch = decodedCell.match(
        /HYPERLINK\("(?:[^"]|"")*","((?:[^"]|"")*)"\)/,
      );
      if (!formulaMatch) {
        throw new Error(`HYPERLINK formula not found: ${sheetName}!${link.cell}`);
      }

      const friendlyName = formulaMatch[1].replaceAll('""', '"');
      const cellTag = cellMatch[1];
      const namespacePrefix = cellTag.includes(":")
        ? `${cellTag.split(":")[0]}:`
        : "";
      const attributes = cellMatch[2].replace(/\s+t="[^"]*"/, "");
      const replacement =
        `<${cellTag}${attributes} t="inlineStr">` +
        `<${namespacePrefix}is><${namespacePrefix}t xml:space="preserve">` +
        `${encodeXml(friendlyName)}</${namespacePrefix}t></${namespacePrefix}is>` +
        `</${cellTag}>`;

      sheetXml = sheetXml.replace(cellPattern, replacement);
      repairedCount += 1;
    }

    zip.file(sheetPath, sheetXml);
  }

  if (repairedCount !== links.length) {
    throw new Error(`Repaired ${repairedCount} of ${links.length} hyperlink cells`);
  }

  const repairedBytes = await zip.generateAsync({
    type: "uint8array",
    compression: "DEFLATE",
    compressionOptions: { level: 6 },
  });
  await fs.writeFile(workbookPath, repairedBytes);
}

for (const link of originalHyperlinks) {
  const sheet = workbook.worksheets.getItem(link.sheet);
  const cell = sheet.getRange(link.cell);
  const currentValue = cell.values?.[0]?.[0];
  const friendlyName = currentValue === null || currentValue === undefined
    ? link.target
    : String(currentValue);
  const currentUrl = friendlyName.match(/https?:\/\/[^\s]+/)?.[0]?.replace(/[),.;]+$/, "");
  const target = link.kind === "internal" ? link.target : (currentUrl ?? link.target);
  cell.formulas = [[
    `=HYPERLINK("${escapeFormulaString(target)}","${escapeFormulaString(friendlyName)}")`,
  ]];
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
await repairHyperlinkCachedValues(outputPath, originalHyperlinks);

const verificationInput = await FileBlob.load(outputPath);
const verificationWorkbook = await SpreadsheetFile.importXlsx(verificationInput);
const verification = await verificationWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#N/A|#NAME\\?",
  options: { useRegex: true, maxResults: 500 },
  maxChars: 30000,
});
await fs.writeFile(
  path.join(outputDir, "formula-error-scan.ndjson"),
  verification.ndjson ?? String(verification),
  "utf8",
);

const previewDir = path.join(outputDir, "final-previews");
await fs.mkdir(previewDir, { recursive: true });
for (const sheet of verificationWorkbook.worksheets.items) {
  const usedRange = sheet.getUsedRange();
  if (!usedRange) continue;
  const preview = await verificationWorkbook.render({
    sheetName: sheet.name,
    autoCrop: "all",
    scale: sheet.name === "FX Daily" ? 0.7 : 1,
    format: "png",
  });
  const safeName = sheet.name.replace(/[<>:"/\\|?*]/g, "_");
  await fs.writeFile(
    path.join(previewDir, `${safeName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

console.log(JSON.stringify({
  outputPath,
  dailyRows: dailyRows.length,
  latestDaily,
  hyperlinkCount: originalHyperlinks.length,
  formulaErrorScan: verification.ndjson ?? String(verification),
}, null, 2));
