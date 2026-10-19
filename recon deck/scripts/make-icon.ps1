Add-Type -AssemblyName System.Drawing
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $root 'assets'
New-Item -ItemType Directory -Force -Path $assets | Out-Null

$size = 256
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::Transparent)

# Dark rounded square
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$r = 56
$path.AddArc(6, 6, $r, $r, 180, 90)
$path.AddArc(250 - $r, 6, $r, $r, 270, 90)
$path.AddArc(250 - $r, 250 - $r, $r, $r, 0, 90)
$path.AddArc(6, 250 - $r, $r, $r, 90, 90)
$path.CloseFigure()

$bg = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
  (New-Object System.Drawing.Point(6, 6)),
  (New-Object System.Drawing.Point(250, 250)),
  ([System.Drawing.Color]::FromArgb(255, 17, 14, 36)),
  ([System.Drawing.Color]::FromArgb(255, 5, 7, 14))
)
$g.FillPath($bg, $path)
$g.DrawPath((New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(80, 167, 139, 250), 2)), $path)

# Hexagon points (pointy top)
$cx = 128.0
$cy = 128.0
$hr = 80.0
$pts = @()
for ($i = 0; $i -lt 6; $i++) {
  $angle = [Math]::PI / 180.0 * (60 * $i - 90)
  $pts += New-Object System.Drawing.PointF(
    [single]($cx + $hr * [Math]::Cos($angle)),
    [single]($cy + $hr * [Math]::Sin($angle))
  )
}

# Soft violet glow and hexagon ring
$glow = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(34, 167, 139, 250), 18)
$g.DrawPolygon($glow, $pts)
$ring = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(200, 167, 139, 250), 4)
$g.DrawPolygon($ring, $pts)

# Spokes from the centre node to every vertex
$spoke = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(120, 94, 234, 212), 3)
foreach ($p in $pts) { $g.DrawLine($spoke, $cx, $cy, $p.X, $p.Y) }

# Outer nodes
foreach ($p in $pts) {
  $halo = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(50, 56, 189, 248))
  $g.FillEllipse($halo, $p.X - 17, $p.Y - 17, 34, 34)
  $node = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 56, 189, 248))
  $g.FillEllipse($node, $p.X - 9, $p.Y - 9, 18, 18)
  $core = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 226, 248, 255))
  $g.FillEllipse($core, $p.X - 3.5, $p.Y - 3.5, 7, 7)
}

# Centre node (teal)
$cHalo = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(70, 94, 234, 212))
$g.FillEllipse($cHalo, $cx - 30, $cy - 30, 60, 60)
$cNode = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 94, 234, 212))
$g.FillEllipse($cNode, $cx - 18, $cy - 18, 36, 36)
$cCore = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 240, 255, 252))
$g.FillEllipse($cCore, $cx - 7, $cy - 7, 14, 14)

$pngPath = Join-Path $assets 'icon.png'
$bmp.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

# ICO container with the embedded 256x256 PNG
$png = [System.IO.File]::ReadAllBytes($pngPath)
$ms = New-Object System.IO.MemoryStream
$bw = New-Object System.IO.BinaryWriter($ms)
$bw.Write([UInt16]0)
$bw.Write([UInt16]1)
$bw.Write([UInt16]1)
$bw.Write([Byte]0)
$bw.Write([Byte]0)
$bw.Write([Byte]0)
$bw.Write([Byte]0)
$bw.Write([UInt16]1)
$bw.Write([UInt16]32)
$bw.Write([UInt32]$png.Length)
$bw.Write([UInt32]22)
$bw.Write($png)
$bw.Flush()
[System.IO.File]::WriteAllBytes((Join-Path $assets 'icon.ico'), $ms.ToArray())
$bw.Dispose()

Write-Output "icon.png: $((Get-Item $pngPath).Length) bytes"
Write-Output "icon.ico: $((Get-Item (Join-Path $assets 'icon.ico')).Length) bytes"
