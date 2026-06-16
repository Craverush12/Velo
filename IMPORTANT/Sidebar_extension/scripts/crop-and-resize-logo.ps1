param(
    [string]$Source = "C:\ThinkVelocity\Sidebar_extension\assets\Velocity_logo.png",
    [string]$OutDir = "C:\ThinkVelocity\Sidebar_extension\assets"
)

Add-Type -AssemblyName System.Drawing

# Load source bitmap with full ARGB so alpha is preserved.
$src = New-Object System.Drawing.Bitmap $Source
Write-Host ("Original: {0}x{1}" -f $src.Width, $src.Height)

# Lock the source bits once for fast alpha scanning.
$rect = New-Object System.Drawing.Rectangle 0, 0, $src.Width, $src.Height
$data = $src.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$stride = $data.Stride
$byteCount = $stride * $src.Height
$buffer = New-Object byte[] $byteCount
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buffer, 0, $byteCount)
$src.UnlockBits($data)

$alphaThreshold = 16
$minX = $src.Width
$minY = $src.Height
$maxX = -1
$maxY = -1

for ($y = 0; $y -lt $src.Height; $y++) {
    $rowStart = $y * $stride
    for ($x = 0; $x -lt $src.Width; $x++) {
        $alpha = $buffer[$rowStart + $x * 4 + 3]
        if ($alpha -gt $alphaThreshold) {
            if ($x -lt $minX) { $minX = $x }
            if ($y -lt $minY) { $minY = $y }
            if ($x -gt $maxX) { $maxX = $x }
            if ($y -gt $maxY) { $maxY = $y }
        }
    }
}

if ($maxX -lt 0) {
    Write-Error "Could not detect any non-transparent pixels in $Source"
    $src.Dispose()
    exit 1
}

$cropW = $maxX - $minX + 1
$cropH = $maxY - $minY + 1
Write-Host ("Content bounds: x={0} y={1} w={2} h={3}" -f $minX, $minY, $cropW, $cropH)

# Pad slightly so the glyph does not sit pressed against the canvas edge,
# then square the crop so resizing keeps the V centered without distortion.
$paddingRatio = 0.08
$square = [Math]::Max($cropW, $cropH)
$padded = [int]([Math]::Ceiling($square * (1 + 2 * $paddingRatio)))

$cropCenterX = $minX + ($cropW / 2.0)
$cropCenterY = $minY + ($cropH / 2.0)
$squareX = [int][Math]::Round($cropCenterX - $padded / 2.0)
$squareY = [int][Math]::Round($cropCenterY - $padded / 2.0)

# Build a square canvas big enough to hold the centered, padded crop.
$canvas = New-Object System.Drawing.Bitmap $padded, $padded, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($canvas)
$g.Clear([System.Drawing.Color]::Transparent)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality

$destRect = New-Object System.Drawing.Rectangle 0, 0, $padded, $padded
$srcRect = New-Object System.Drawing.Rectangle $squareX, $squareY, $padded, $padded
$g.DrawImage($src, $destRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$src.Dispose()

# Export size-specific icons + a tight master copy for the in-panel UI.
$sizes = @{
    "icon16.png"  = 16
    "icon32.png"  = 32
    "icon48.png"  = 48
    "icon128.png" = 128
    "Velocity_logo.png" = $padded
}

foreach ($entry in $sizes.GetEnumerator()) {
    $target = Join-Path $OutDir $entry.Key
    $size = $entry.Value
    $out = New-Object System.Drawing.Bitmap $size, $size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $og = [System.Drawing.Graphics]::FromImage($out)
    $og.Clear([System.Drawing.Color]::Transparent)
    $og.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $og.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $og.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $og.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $og.DrawImage($canvas, (New-Object System.Drawing.Rectangle 0, 0, $size, $size))
    $og.Dispose()
    $out.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
    $out.Dispose()
    Write-Host ("Wrote {0} ({1}x{1})" -f $target, $size)
}

$canvas.Dispose()
