Add-Type -AssemblyName System.Drawing

$projectRoot = Split-Path -Parent $PSScriptRoot
$ruleOutputRoot = Join-Path $projectRoot "outputs_rule"
$figureOutputDir = Join-Path $projectRoot "report\figures"

if (-not (Test-Path -LiteralPath $figureOutputDir)) {
    New-Item -ItemType Directory -Path $figureOutputDir | Out-Null
}

function Get-MetricMap {
    param(
        [string]$CsvPath,
        [string]$MetricName
    )

    $map = @{}
    foreach ($row in (Import-Csv -LiteralPath $CsvPath)) {
        $map[$row.Antibiotic] = [double]$row.$MetricName
    }
    return $map
}

function Draw-RuleMetricFigure {
    param(
        [hashtable]$StrictMap,
        [hashtable]$BroadMap,
        [string[]]$Antibiotics,
        [string]$MetricLabel,
        [string]$Title,
        [string]$OutputPath
    )

    $width = 1800
    $height = 1100

    $leftMargin = 330
    $rightMargin = 250
    $topMargin = 120
    $bottomMargin = 90

    $plotWidth = $width - $leftMargin - $rightMargin
    $plotHeight = $height - $topMargin - $bottomMargin

    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.Clear([System.Drawing.Color]::White)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

    $titleFont = New-Object System.Drawing.Font("Arial", 20, [System.Drawing.FontStyle]::Bold)
    $axisFont = New-Object System.Drawing.Font("Arial", 13, [System.Drawing.FontStyle]::Bold)
    $labelFont = New-Object System.Drawing.Font("Arial", 10)
    $legendFont = New-Object System.Drawing.Font("Arial", 10)
    $legendTitleFont = New-Object System.Drawing.Font("Arial", 12, [System.Drawing.FontStyle]::Bold)

    $axisPen = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 1.3)
    $gridPen = New-Object System.Drawing.Pen([System.Drawing.Color]::LightGray, 1.0)
    $gridPen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
    $separatorPen = New-Object System.Drawing.Pen([System.Drawing.Color]::Gainsboro, 1.0)
    $strictBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(231, 111, 81))
    $broadBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(233, 196, 106))
    $textBrush = [System.Drawing.Brushes]::Black
    $whiteBrush = [System.Drawing.Brushes]::White

    $titleSize = $graphics.MeasureString($Title, $titleFont)
    $graphics.DrawString($Title, $titleFont, $textBrush, ($width - $titleSize.Width) / 2, 32)

    $plotLeft = $leftMargin
    $plotRight = $leftMargin + $plotWidth
    $plotTop = $topMargin
    $plotBottom = $topMargin + $plotHeight

    for ($tick = 0; $tick -le 10; $tick++) {
        $value = $tick / 10.0
        $x = $plotLeft + ($value * $plotWidth)
        $graphics.DrawLine($gridPen, $x, $plotTop, $x, $plotBottom)
        $tickText = $value.ToString("0.0")
        $tickSize = $graphics.MeasureString($tickText, $labelFont)
        $graphics.DrawString($tickText, $labelFont, $textBrush, $x - ($tickSize.Width / 2), $plotBottom + 10)
    }

    $graphics.DrawLine($axisPen, $plotLeft, $plotTop, $plotLeft, $plotBottom)
    $graphics.DrawLine($axisPen, $plotLeft, $plotBottom, $plotRight, $plotBottom)

    $groupHeight = $plotHeight / $Antibiotics.Count
    $barHeight = [Math]::Min(18.0, $groupHeight * 0.28)
    $barGap = [Math]::Max(6.0, $barHeight * 0.35)

    for ($index = 0; $index -lt $Antibiotics.Count; $index++) {
        $antibiotic = $Antibiotics[$index]
        $centerY = $plotTop + (($index + 0.5) * $groupHeight)

        $broadTop = $centerY - $barGap / 2 - $barHeight
        $strictTop = $centerY + $barGap / 2

        $broadWidth = $BroadMap[$antibiotic] * $plotWidth
        $strictWidth = $StrictMap[$antibiotic] * $plotWidth

        $graphics.FillRectangle($broadBrush, $plotLeft, $broadTop, $broadWidth, $barHeight)
        $graphics.DrawRectangle($axisPen, $plotLeft, $broadTop, $broadWidth, $barHeight)
        $graphics.FillRectangle($strictBrush, $plotLeft, $strictTop, $strictWidth, $barHeight)
        $graphics.DrawRectangle($axisPen, $plotLeft, $strictTop, $strictWidth, $barHeight)

        $graphics.DrawLine($separatorPen, $plotLeft, $plotTop + (($index + 1) * $groupHeight), $plotRight, $plotTop + (($index + 1) * $groupHeight))

        $labelSize = $graphics.MeasureString($antibiotic, $labelFont)
        $graphics.DrawString($antibiotic, $labelFont, $textBrush, $plotLeft - $labelSize.Width - 8, $centerY - ($labelSize.Height / 2))
    }

    $xLabelSize = $graphics.MeasureString($MetricLabel, $axisFont)
    $graphics.DrawString($MetricLabel, $axisFont, $textBrush, $plotLeft + (($plotWidth - $xLabelSize.Width) / 2), $height - 45)

    $graphics.TranslateTransform(55, $plotTop + ($plotHeight / 2))
    $graphics.RotateTransform(-90)
    $yLabelSize = $graphics.MeasureString("Antibiotic", $axisFont)
    $graphics.DrawString("Antibiotic", $axisFont, $textBrush, -($yLabelSize.Width / 2), -($yLabelSize.Height / 2))
    $graphics.ResetTransform()

    $legendX = $plotRight + 45
    $legendY = $plotTop + 10
    $graphics.DrawString("Scope", $legendTitleFont, $textBrush, $legendX, $legendY)
    $graphics.FillRectangle($broadBrush, $legendX, $legendY + 38, 26, 16)
    $graphics.DrawRectangle($axisPen, $legendX, $legendY + 38, 26, 16)
    $graphics.DrawString("broad rule", $legendFont, $textBrush, $legendX + 36, $legendY + 35)
    $graphics.FillRectangle($strictBrush, $legendX, $legendY + 68, 26, 16)
    $graphics.DrawRectangle($axisPen, $legendX, $legendY + 68, 26, 16)
    $graphics.DrawString("strict rule", $legendFont, $textBrush, $legendX + 36, $legendY + 65)

    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)

    $strictBrush.Dispose()
    $broadBrush.Dispose()
    $gridPen.Dispose()
    $separatorPen.Dispose()
    $axisPen.Dispose()
    $titleFont.Dispose()
    $axisFont.Dispose()
    $labelFont.Dispose()
    $legendFont.Dispose()
    $legendTitleFont.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
}

$strictCsv = Join-Path $ruleOutputRoot "strict\metrics.csv"
$broadCsv = Join-Path $ruleOutputRoot "broad\metrics.csv"

$antibiotics = (Import-Csv -LiteralPath $strictCsv | ForEach-Object { $_.Antibiotic })

$strictRecallMap = Get-MetricMap -CsvPath $strictCsv -MetricName "recall"
$broadRecallMap = Get-MetricMap -CsvPath $broadCsv -MetricName "recall"
$strictPrecisionMap = Get-MetricMap -CsvPath $strictCsv -MetricName "precision"
$broadPrecisionMap = Get-MetricMap -CsvPath $broadCsv -MetricName "precision"

Draw-RuleMetricFigure `
    -StrictMap $strictRecallMap `
    -BroadMap $broadRecallMap `
    -Antibiotics $antibiotics `
    -MetricLabel "Recall" `
    -Title "Rule-Based Recall Comparison By Antibiotic And Scope" `
    -OutputPath (Join-Path $figureOutputDir "rule_recall_by_scope_fixed.png")

Draw-RuleMetricFigure `
    -StrictMap $strictPrecisionMap `
    -BroadMap $broadPrecisionMap `
    -Antibiotics $antibiotics `
    -MetricLabel "Precision" `
    -Title "Rule-Based Precision Comparison By Antibiotic And Scope" `
    -OutputPath (Join-Path $figureOutputDir "rule_precision_by_scope_fixed.png")
