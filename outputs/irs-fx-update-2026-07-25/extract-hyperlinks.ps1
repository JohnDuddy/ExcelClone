param(
    [Parameter(Mandatory = $true)]
    [string] $WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputPath
)

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Read-ZipEntryText {
    param(
        [System.IO.Compression.ZipArchive] $Archive,
        [string] $EntryName
    )

    $entry = $Archive.GetEntry($EntryName)
    if ($null -eq $entry) {
        return $null
    }

    $reader = [System.IO.StreamReader]::new($entry.Open())
    try {
        return $reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
    }
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($WorkbookPath)
try {
    [xml] $workbookXml = Read-ZipEntryText -Archive $archive -EntryName "xl/workbook.xml"
    [xml] $workbookRelsXml = Read-ZipEntryText -Archive $archive -EntryName "xl/_rels/workbook.xml.rels"

    $workbookNs = [System.Xml.XmlNamespaceManager]::new($workbookXml.NameTable)
    $workbookNs.AddNamespace("m", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    $workbookNs.AddNamespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")

    $relationshipTargets = @{}
    foreach ($rel in $workbookRelsXml.Relationships.Relationship) {
        $relationshipTargets[$rel.Id] = $rel.Target
    }

    $links = [System.Collections.Generic.List[object]]::new()
    foreach ($sheetNode in $workbookXml.SelectNodes("//m:sheets/m:sheet", $workbookNs)) {
        $sheetName = $sheetNode.GetAttribute("name")
        $relationshipId = $sheetNode.GetAttribute(
            "id",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        )
        $worksheetTarget = $relationshipTargets[$relationshipId].Replace("\", "/")
        if ($worksheetTarget.StartsWith("/")) {
            $worksheetEntry = $worksheetTarget.TrimStart("/")
        }
        elseif ($worksheetTarget.StartsWith("xl/")) {
            $worksheetEntry = $worksheetTarget
        }
        else {
            $worksheetEntry = "xl/$worksheetTarget"
        }

        [xml] $worksheetXml = Read-ZipEntryText -Archive $archive -EntryName $worksheetEntry
        if ($null -eq $worksheetXml) {
            continue
        }

        $worksheetNs = [System.Xml.XmlNamespaceManager]::new($worksheetXml.NameTable)
        $worksheetNs.AddNamespace("m", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")

        $sheetRelsEntry = "xl/worksheets/_rels/$([System.IO.Path]::GetFileName($worksheetEntry)).rels"
        $sheetRelationships = @{}
        $sheetRelsText = Read-ZipEntryText -Archive $archive -EntryName $sheetRelsEntry
        if ($null -ne $sheetRelsText) {
            [xml] $sheetRelsXml = $sheetRelsText
            foreach ($rel in $sheetRelsXml.Relationships.Relationship) {
                $sheetRelationships[$rel.Id] = $rel.Target
            }
        }

        foreach ($linkNode in $worksheetXml.SelectNodes("//m:hyperlinks/m:hyperlink", $worksheetNs)) {
            $cell = $linkNode.GetAttribute("ref")
            $location = $linkNode.GetAttribute("location")
            $linkRelationshipId = $linkNode.GetAttribute(
                "id",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            )

            if ($location) {
                $target = "#$location"
                $kind = "internal"
            }
            else {
                $target = $sheetRelationships[$linkRelationshipId]
                $kind = "external"
            }

            $links.Add([pscustomobject]@{
                sheet = $sheetName
                cell = $cell
                target = $target
                kind = $kind
            })
        }
    }

    $links | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $OutputPath -Encoding utf8
    Write-Output "Extracted $($links.Count) hyperlinks to $OutputPath"
}
finally {
    $archive.Dispose()
}
