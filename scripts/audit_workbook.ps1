<#
Audit read-only untuk SERI TABUNG.xlsm (F0 - gas-wayan-python).

Tujuan: mereproduksi secara independen hitungan, checksum, missing value, duplikat,
dan masalah tanggal dari ../Gas Wayan/docs/workbook-audit.md, tanpa menginstal Python
dan tanpa membuka workbook di Excel (menghindari risiko menjalankan VBA).

Cara kerja: file .xlsm dibaca sebagai paket ZIP/OOXML read-only (System.IO.Compression),
lalu XML tiap bagian diparse dengan XmlReader (streaming) dan regex ringan per baris.
Skrip tidak pernah menulis ke SERI TABUNG.xlsm dan tidak menjalankan macro apa pun.

Output: satu objek JSON agregat (hitungan saja, tanpa nilai relasi/tabung mentah)
ditulis ke file yang diberikan lewat -OutFile. Tidak ada data pelanggan yang dicetak
ke konsol supaya aman dari log percakapan.

Pemakaian:
  pwsh -NoProfile -File scripts/audit_workbook.ps1 -WorkbookPath "..\SERI TABUNG.xlsm" -OutFile "docs/reports/f0-audit-raw.json"
#>
param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$OutFile
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Decode-XmlText([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return $s }
    $s = $s -replace '&lt;', '<' -replace '&gt;', '>' -replace '&quot;', '"' -replace '&apos;', "'"
    $s = [regex]::Replace($s, '&#x([0-9A-Fa-f]+);', { param($m) [char]([Convert]::ToInt32($m.Groups[1].Value, 16)) })
    $s = [regex]::Replace($s, '&#(\d+);', { param($m) [char]([int]$m.Groups[1].Value) })
    $s = $s -replace '&amp;', '&'
    return $s
}

function Get-ZipEntryText($zip, [string]$name) {
    $entry = $zip.GetEntry($name)
    if (-not $entry) { return $null }
    $sr = New-Object System.IO.StreamReader($entry.Open())
    try { return $sr.ReadToEnd() } finally { $sr.Close() }
}

$fullPath = (Resolve-Path -LiteralPath $WorkbookPath).Path

# --- checksum -------------------------------------------------------------
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $fullPath).Hash

$zip = [System.IO.Compression.ZipFile]::OpenRead($fullPath)

try {
    # --- map sheet name -> worksheet part via workbook.xml + rels --------
    $wbText = Get-ZipEntryText $zip 'xl/workbook.xml'
    $relsText = Get-ZipEntryText $zip 'xl/_rels/workbook.xml.rels'

    $sheetMeta = @{}
    foreach ($m in [regex]::Matches($wbText, '<sheet\s+name="([^"]*)"\s+sheetId="(\d+)"(?:\s+state="([^"]*)")?\s+r:id="(rId\d+)"\s*/>')) {
        $sheetMeta[$m.Groups[1].Value] = [pscustomobject]@{
            SheetId = $m.Groups[2].Value
            State   = $m.Groups[3].Value
            RId     = $m.Groups[4].Value
        }
    }
    # attribute order in the source file can vary; fall back to a tolerant parse if needed
    if ($sheetMeta.Count -eq 0) {
        foreach ($m in [regex]::Matches($wbText, '<sheet\b[^/]*/>')) {
            $tag = $m.Value
            $name = [regex]::Match($tag, 'name="([^"]*)"').Groups[1].Value
            $rid = [regex]::Match($tag, 'r:id="(rId\d+)"').Groups[1].Value
            $state = [regex]::Match($tag, 'state="([^"]*)"').Groups[1].Value
            $sheetMeta[$name] = [pscustomobject]@{ SheetId = $null; State = $state; RId = $rid }
        }
    }

    $ridToTarget = @{}
    foreach ($m in [regex]::Matches($relsText, '<Relationship\s+Id="(rId\d+)"[^>]*Target="([^"]*)"')) {
        $ridToTarget[$m.Groups[1].Value] = $m.Groups[2].Value
    }

    function Resolve-SheetPart([string]$sheetName) {
        $meta = $sheetMeta[$sheetName]
        if (-not $meta) { throw "Sheet '$sheetName' tidak ditemukan di workbook.xml" }
        $target = $ridToTarget[$meta.RId]
        return [pscustomobject]@{ Path = "xl/$target"; State = $meta.State }
    }

    $dbPart = Resolve-SheetPart 'Database'
    $searchPart = Resolve-SheetPart 'SearchData'

    # --- shared strings ----------------------------------------------------
    $sstText = Get-ZipEntryText $zip 'xl/sharedStrings.xml'
    $sharedStrings = New-Object System.Collections.Generic.List[string]
    if ($sstText) {
        foreach ($m in [regex]::Matches($sstText, '<si>(.*?)</si>', [System.Text.RegularExpressions.RegexOptions]::Singleline)) {
            $inner = $m.Groups[1].Value
            $parts = [regex]::Matches($inner, '<t[^>]*>(.*?)</t>', [System.Text.RegularExpressions.RegexOptions]::Singleline) |
                ForEach-Object { Decode-XmlText $_.Groups[1].Value }
            $sharedStrings.Add(($parts -join ''))
        }
    }

    # --- styles: which style indices render as a date ---------------------
    $stylesText = Get-ZipEntryText $zip 'xl/styles.xml'
    $customNumFmts = @{}
    foreach ($m in [regex]::Matches($stylesText, '<numFmt\s+numFmtId="(\d+)"\s+formatCode="([^"]*)"')) {
        $customNumFmts[$m.Groups[1].Value] = Decode-XmlText $m.Groups[2].Value
    }
    $builtinDateIds = @('14', '15', '16', '17', '22', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '45', '46', '47', '50', '51', '52', '53', '54', '55', '56', '57', '58')
    function Test-DateFormatCode([string]$code) {
        if (-not $code) { return $false }
        if ($code -match '[hHsS]') { return $false } # time-only formats: not a "date"
        return [bool]([regex]::IsMatch($code, '[dDmMyY]'))
    }
    $cellXfsBlock = [regex]::Match($stylesText, '<cellXfs[^>]*>(.*?)</cellXfs>', [System.Text.RegularExpressions.RegexOptions]::Singleline).Groups[1].Value
    $xfNumFmtId = New-Object System.Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($cellXfsBlock, '<xf\b[^>]*numFmtId="(\d+)"[^>]*/?>')) {
        $xfNumFmtId.Add($m.Groups[1].Value)
    }
    $dateStyleIndex = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($i = 0; $i -lt $xfNumFmtId.Count; $i++) {
        $fmtId = $xfNumFmtId[$i]
        $isDate = $false
        if ($builtinDateIds -contains $fmtId) { $isDate = $true }
        elseif ($customNumFmts.ContainsKey($fmtId)) { $isDate = Test-DateFormatCode $customNumFmts[$fmtId] }
        if ($isDate) { [void]$dateStyleIndex.Add($i) }
    }

    # --- cell parsing helpers ----------------------------------------------
    $cellRegex = [regex]'<c\s+r="([A-Z]+)(\d+)"(?:[^>]*?\bs="(\d+)")?(?:[^>]*?\bt="([a-zA-Z]+)")?[^>]*?(?:/>|>(?:<v>(.*?)</v>|<is>(.*?)</is>)?</c>)'

    function Get-CellValue($t, $rawInner, $isXml, $sharedStrings) {
        if ($t -eq 's') {
            $idx = [int]$rawInner
            if ($idx -ge 0 -and $idx -lt $sharedStrings.Count) { return $sharedStrings[$idx] }
            return ''
        } elseif ($t -eq 'inlineStr') {
            $tm = [regex]::Match($isXml, '<t[^>]*>(.*?)</t>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
            if ($tm.Success) { return Decode-XmlText $tm.Groups[1].Value }
            return ''
        } elseif ($t -eq 'str' -or $t -eq 'b' -or $t -eq 'e' -or [string]::IsNullOrEmpty($t)) {
            return Decode-XmlText $rawInner
        }
        return Decode-XmlText $rawInner
    }

    function New-ColumnStat {
        [pscustomobject]@{
            Empty              = 0
            NonEmpty           = 0
            NativeDate         = 0
            NumericNonDate     = 0
            StringNonEmpty     = 0
            LeadingTrailingWs  = 0
            ValueCounts        = (New-Object 'System.Collections.Generic.Dictionary[string,int]' ([System.StringComparer]::Ordinal))   # trimmed-value -> count, case-sensitive (PowerShell @{} default ke case-insensitive)
            ParseableDate      = 0
            UnparseableDate    = 0
        }
    }

    # policy tanggal: day-first konservatif, terima separator / . -, tanpa menebak tanggal mustahil
    function Try-ParseLegacyDate([string]$raw) {
        $s = $raw.Trim()
        $m = [regex]::Match($s, '^(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})$')
        if (-not $m.Success) { return $null }
        $d = [int]$m.Groups[1].Value
        $mo = [int]$m.Groups[2].Value
        $y = [int]$m.Groups[3].Value
        if ($y -lt 100) { $y += 2000 }
        if ($mo -lt 1 -or $mo -gt 12) { return $null }
        if ($d -lt 1 -or $d -gt 31) { return $null }
        try { return Get-Date -Year $y -Month $mo -Day $d } catch { return $null }
    }

    $excelEpoch = Get-Date -Year 1899 -Month 12 -Day 30

    function Get-DateFromNative([double]$serial) {
        return $excelEpoch.AddDays($serial)
    }

    # --- stream Database rows ----------------------------------------------
    $dbEntry = $zip.GetEntry($dbPart.Path)
    $reader = [System.Xml.XmlReader]::Create($dbEntry.Open())

    $colA = New-ColumnStat  # Nomor
    $colB = New-ColumnStat  # Nomor Tabung
    $colC = New-ColumnStat  # Nama Relasi
    $colD = New-ColumnStat  # Tanggal Pengiriman
    $colE = New-ColumnStat  # Tanggal Pengembalian
    $colF = New-ColumnStat  # Jenis Gas

    $statusKeywordCounts = New-Object 'System.Collections.Generic.Dictionary[string,int]' ([System.StringComparer]::Ordinal)
    $knownStatusKeywords = @('K', 'KEMBALI', 'SDH KEMBALI', 'SDH BALIK', 'GANTI TABUNG', 'HILANG', 'TUKAR TABUNG', 'TABUNG DIGANTI', 'CEK')

    $totalRowElements = 0
    $totalDataRows = 0
    $totalBlankRows = 0
    $maxRowSeen = 1
    $countA_nonblank = 0
    $rowsWithBothDates = 0
    $rowsReturnedBeforeSent = 0
    $businessDupKey = New-Object 'System.Collections.Generic.Dictionary[string,int]' ([System.StringComparer]::Ordinal)   # B|C|D|E|F normalized -> count
    $flaggedRows = @{}      # rows 10599..10601 presence

    $tabungDates = $null # not used globally

    # sheetData tidak berisi whitespace antar-<row>, jadi setelah ReadOuterXml() reader sudah
    # berada tepat di elemen <row> berikutnya. ReadToFollowing() TIDAK menguji posisi saat ini -
    # ia selalu mencari kemunculan berikutnya - jadi memanggilnya lagi di sini akan melewati
    # satu baris setiap iterasi. Move-ToNextRow menghindari itu.
    function Move-ToNextRow($r) {
        if ($r.NodeType -eq [System.Xml.XmlNodeType]::Element -and $r.LocalName -eq 'row') { return $true }
        return $r.ReadToFollowing('row')
    }

    while (Move-ToNextRow $reader) {
            $rowNum = [int]$reader.GetAttribute('r')
            if ($rowNum -gt $maxRowSeen) { $maxRowSeen = $rowNum }
            $rowOuter = $reader.ReadOuterXml()
            $totalRowElements++
            if ($rowNum -eq 1) { continue } # header

            $vals = @{ A = ''; B = ''; C = ''; D = ''; E = ''; F = '' }
            $rawVals = @{ A = ''; B = ''; C = ''; D = ''; E = ''; F = '' }
            $isNative = @{ D = $false; E = $false }
            $present = @{ A = $false; B = $false; C = $false; D = $false; E = $false; F = $false }

            foreach ($cm in $cellRegex.Matches($rowOuter)) {
                $col = $cm.Groups[1].Value
                if (-not $vals.ContainsKey($col)) { continue }
                $styleIdx = $null
                if ($cm.Groups[3].Success) { $styleIdx = [int]$cm.Groups[3].Value }
                $t = $null
                if ($cm.Groups[4].Success) { $t = $cm.Groups[4].Value }
                $vInner = $cm.Groups[5].Value
                $isInner = $cm.Groups[6].Value
                if ([string]::IsNullOrEmpty($vInner) -and [string]::IsNullOrEmpty($isInner)) {
                    # cell present but blank (no <v>, no <is>) -> treat as absent value
                    $present[$col] = $false
                    continue
                }
                $present[$col] = $true
                $val = Get-CellValue $t $vInner $isInner $sharedStrings
                $rawVals[$col] = $val
                if (($col -eq 'D' -or $col -eq 'E') -and [string]::IsNullOrEmpty($t)) {
                    $num = 0.0
                    if ([double]::TryParse($vInner, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$num)) {
                        if ($styleIdx -ne $null -and $dateStyleIndex.Contains($styleIdx)) {
                            $isNative[$col] = $true
                            $vals[$col] = (Get-DateFromNative $num)
                        } else {
                            $vals[$col] = $num
                        }
                    }
                } else {
                    $vals[$col] = $val
                }
            }

            $anyData = $present.Values -contains $true
            if ($anyData) { $totalDataRows++ } else { $totalBlankRows++ }

            if ($rowNum -ge 10599 -and $rowNum -le 10601) {
                $flaggedRows[[string]$rowNum] = $anyData
            }

            # --- Column A: Nomor ---
            if ($present['A']) {
                $countA_nonblank++
                $colA.NonEmpty++
                $key = [string]$rawVals['A']
                if ($colA.ValueCounts.ContainsKey($key)) { $colA.ValueCounts[$key]++ } else { $colA.ValueCounts[$key] = 1 }
            } else { $colA.Empty++ }

            # --- Column B: Nomor Tabung ---
            $bRaw = [string]$rawVals['B']
            if ($present['B'] -and $bRaw.Trim() -ne '') {
                $colB.NonEmpty++
                if ($bRaw -ne $bRaw.Trim()) { $colB.LeadingTrailingWs++ }
                $bTrim = $bRaw.Trim()
                if ($colB.ValueCounts.ContainsKey($bTrim)) { $colB.ValueCounts[$bTrim]++ } else { $colB.ValueCounts[$bTrim] = 1 }
            } else { $colB.Empty++ }

            # --- Column C: Nama Relasi ---
            $cRaw = [string]$rawVals['C']
            if ($present['C'] -and $cRaw.Trim() -ne '') {
                $colC.NonEmpty++
                if ($cRaw -ne $cRaw.Trim()) { $colC.LeadingTrailingWs++ }
                $cTrim = $cRaw.Trim()
                $cNorm = ([regex]::Replace($cTrim, '\s+', ' ')).ToUpperInvariant()
                if ($colC.ValueCounts.ContainsKey($cTrim)) { $colC.ValueCounts[$cTrim]++ } else { $colC.ValueCounts[$cTrim] = 1 }
                # simpan hitungan normalized terpisah lewat properti tambahan
                if (-not $colC.PSObject.Properties.Match('NormCounts').Count) { $colC | Add-Member -NotePropertyName NormCounts -NotePropertyValue (New-Object 'System.Collections.Generic.Dictionary[string,int]' ([System.StringComparer]::Ordinal)) }
                if ($colC.NormCounts.ContainsKey($cNorm)) { $colC.NormCounts[$cNorm]++ } else { $colC.NormCounts[$cNorm] = 1 }
            } else { $colC.Empty++ }

            # --- Column D & E: tanggal ---
            foreach ($pair in @(@{ Col = 'D'; Stat = $colD }, @{ Col = 'E'; Stat = $colE })) {
                $c = $pair.Col; $stat = $pair.Stat
                $raw = $rawVals[$c]
                $rawStr = [string]$raw
                if (-not $present[$c] -or $rawStr.Trim() -eq '') {
                    $stat.Empty++
                    continue
                }
                $stat.NonEmpty++
                if ($isNative[$c]) {
                    $stat.NativeDate++
                } else {
                    if ($rawStr -ne $rawStr.Trim()) { $stat.LeadingTrailingWs++ }
                    $stat.StringNonEmpty++
                    $parsed = Try-ParseLegacyDate $rawStr
                    if ($parsed) { $stat.ParseableDate++ } else {
                        $stat.UnparseableDate++
                        $kw = $rawStr.Trim().ToUpperInvariant()
                        if ($knownStatusKeywords -contains $kw) {
                            if ($statusKeywordCounts.ContainsKey($kw)) { $statusKeywordCounts[$kw]++ } else { $statusKeywordCounts[$kw] = 1 }
                        }
                    }
                }
            }

            # chronology check: E < D
            $dDate = $null; $eDate = $null
            if ($isNative['D']) { $dDate = $vals['D'] }
            elseif ($present['D']) { $p = Try-ParseLegacyDate ([string]$rawVals['D']); if ($p) { $dDate = $p } }
            if ($isNative['E']) { $eDate = $vals['E'] }
            elseif ($present['E']) { $p = Try-ParseLegacyDate ([string]$rawVals['E']); if ($p) { $eDate = $p } }
            if ($dDate -and $eDate) {
                $rowsWithBothDates++
                if ($eDate -lt $dDate) { $rowsReturnedBeforeSent++ }
            }

            # --- Column F: Jenis Gas ---
            $fRaw = [string]$rawVals['F']
            if ($present['F'] -and $fRaw.Trim() -ne '') {
                $colF.NonEmpty++
                if ($fRaw -ne $fRaw.Trim()) { $colF.LeadingTrailingWs++ }
                $fTrim = $fRaw.Trim()
                $fNorm = ([regex]::Replace($fTrim, '\s+', ' ')).ToUpperInvariant()
                if ($colF.ValueCounts.ContainsKey($fTrim)) { $colF.ValueCounts[$fTrim]++ } else { $colF.ValueCounts[$fTrim] = 1 }
                if (-not $colF.PSObject.Properties.Match('NormCounts').Count) { $colF | Add-Member -NotePropertyName NormCounts -NotePropertyValue (New-Object 'System.Collections.Generic.Dictionary[string,int]' ([System.StringComparer]::Ordinal)) }
                if ($colF.NormCounts.ContainsKey($fNorm)) { $colF.NormCounts[$fNorm]++ } else { $colF.NormCounts[$fNorm] = 1 }
            } else { $colF.Empty++ }

            # --- kandidat duplikat bisnis (abaikan Nomor) ---
            $dupKey = "$($bRaw.Trim())|$(([regex]::Replace($cRaw.Trim(),'\s+',' ')).ToUpperInvariant())|$($rawVals['D'])|$($rawVals['E'])|$($fRaw.Trim())"
            if ($businessDupKey.ContainsKey($dupKey)) { $businessDupKey[$dupKey]++ } else { $businessDupKey[$dupKey] = 1 }
    }
    $reader.Close()

    # --- duplicate summaries ---
    $dupGroupsA = @($colA.ValueCounts.GetEnumerator() | Where-Object { $_.Value -gt 1 })
    $dupExtraA = ($dupGroupsA | ForEach-Object { $_.Value - 1 } | Measure-Object -Sum).Sum
    if (-not $dupExtraA) { $dupExtraA = 0 }

    $dupGroupsB = @($colB.ValueCounts.GetEnumerator() | Where-Object { $_.Value -gt 1 })
    $maxB = ($colB.ValueCounts.Values | Measure-Object -Maximum).Maximum

    $bizDupGroups = @($businessDupKey.GetEnumerator() | Where-Object { $_.Value -gt 1 })
    $bizDupExtra = ($bizDupGroups | ForEach-Object { $_.Value - 1 } | Measure-Object -Sum).Sum
    if (-not $bizDupExtra) { $bizDupExtra = 0 }

    $cNormUnique = 0
    if ($colC.PSObject.Properties.Match('NormCounts').Count) { $cNormUnique = $colC.NormCounts.Count }
    $fNormUnique = 0
    $fNormTop = @()
    if ($colF.PSObject.Properties.Match('NormCounts').Count) {
        $fNormUnique = $colF.NormCounts.Count
        $fNormTop = $colF.NormCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 15 | ForEach-Object { [pscustomobject]@{ Value = $_.Key; Count = $_.Value } }
    }

    # --- SearchData sheet (cache, must NOT be treated as extra transactions) ---
    $searchEntry = $zip.GetEntry($searchPart.Path)
    $searchXmlReader = [System.Xml.XmlReader]::Create($searchEntry.Open())
    $searchRowCount = 0
    while ($searchXmlReader.Read()) {
        if ($searchXmlReader.NodeType -eq [System.Xml.XmlNodeType]::Element -and $searchXmlReader.LocalName -eq 'row') {
            $searchRowCount++
        }
    }
    $searchXmlReader.Close()

    $result = [pscustomobject]@{
        source = [pscustomobject]@{
            path      = $fullPath
            sha256    = $hash
            checkedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
        }
        sheets = [pscustomobject]@{
            databasePart   = $dbPart.Path
            searchDataPart = $searchPart.Path
            searchDataHidden = ($searchPart.State -eq 'hidden')
            searchDataRowElements = $searchRowCount   # termasuk header jika ada; cache, bukan transaksi
        }
        rows = [pscustomobject]@{
            dimensionMaxRow          = $maxRowSeen
            rowElementsInXml         = $totalRowElements   # termasuk header
            dataRows                 = $totalDataRows       # baris 2..N dengan >=1 sel terisi
            blankRowsWithElement     = $totalBlankRows      # baris 2..N ber-elemen <row> tapi enam kolom kosong
            physicalRowsAfterHeader  = ($maxRowSeen - 1)     # dimensionMaxRow - 1 (baris 2..dimensionMaxRow)
            blankRowsTotal           = ($maxRowSeen - 1 - $totalDataRows)  # termasuk baris tanpa elemen <row> sama sekali
            countA_nonBlank          = $countA_nonblank     # setara COUNTA(Database!A:A) - 1 (tanpa header)
        }
        columnA_Nomor = [pscustomobject]@{
            empty              = $colA.Empty
            nonEmpty           = $colA.NonEmpty
            uniqueValues       = $colA.ValueCounts.Count
            duplicateGroups    = $dupGroupsA.Count
            duplicateExtraRows = $dupExtraA
        }
        columnB_NomorTabung = [pscustomobject]@{
            empty                = $colB.Empty
            nonEmptyAfterTrim    = $colB.NonEmpty
            uniqueAfterTrim      = $colB.ValueCounts.Count
            serialsWithMultiple  = $dupGroupsB.Count
            maxRecordsPerSerial  = $maxB
            leadingTrailingSpace = $colB.LeadingTrailingWs
        }
        columnC_NamaRelasi = [pscustomobject]@{
            empty                       = $colC.Empty
            nonEmpty                    = $colC.NonEmpty
            uniqueAfterTrimOnly         = $colC.ValueCounts.Count
            uniqueAfterTrimUpperCollapse = $cNormUnique
            leadingTrailingSpace        = $colC.LeadingTrailingWs
        }
        columnD_TanggalPengiriman = [pscustomobject]@{
            empty               = $colD.Empty
            nativeExcelDate     = $colD.NativeDate
            stringNonEmpty      = $colD.StringNonEmpty
            parseableString     = $colD.ParseableDate
            unparseableString   = $colD.UnparseableDate
            leadingTrailingSpace = $colD.LeadingTrailingWs
        }
        columnE_TanggalPengembalian = [pscustomobject]@{
            empty               = $colE.Empty
            nativeExcelDate     = $colE.NativeDate
            stringNonEmpty      = $colE.StringNonEmpty
            parseableString     = $colE.ParseableDate
            unparseableString   = $colE.UnparseableDate
            leadingTrailingSpace = $colE.LeadingTrailingWs
            statusKeywordCounts = $statusKeywordCounts
        }
        columnF_JenisGas = [pscustomobject]@{
            empty                      = $colF.Empty
            nonEmpty                   = $colF.NonEmpty
            uniqueAfterTrimOnly        = $colF.ValueCounts.Count
            uniqueAfterSimpleNormalize = $fNormUnique
            leadingTrailingSpace       = $colF.LeadingTrailingWs
            top15Normalized            = $fNormTop
        }
        businessDuplicates_IgnoringNomor = [pscustomobject]@{
            groups    = $bizDupGroups.Count
            extraRows = $bizDupExtra
        }
        chronology = [pscustomobject]@{
            rowsWithBothDatesResolved = $rowsWithBothDates
            returnBeforeSendCandidates = $rowsReturnedBeforeSent
        }
        flaggedRows_10599_10601 = $flaggedRows
    }

    $result | ConvertTo-Json -Depth 8 | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "OK - hasil ditulis ke $OutFile"
    Write-Host ("sha256={0}" -f $hash)
}
finally {
    $zip.Dispose()
}
