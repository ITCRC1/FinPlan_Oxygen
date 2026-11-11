param([string]$Libro, [switch]$Refrescar, [string[]]$Solo = @())
# Agrega Posiciones, Checkbook Planilla, OPEX, Costos y Estadisticas al libro en vivo (owner, 2026-11-11).
# Misma mecanica que add_queries.ps1: una consulta por pestana que lee tVersiones.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$defs = @(
  @{ q = "Posiciones";        hoja = "Posiciones";        tabla = "tPosiciones"; m = "posiciones.m"; d = "Posiciones por mes: FTE y costo, con nombre y salario" },
  @{ q = "CheckbookPlanilla"; hoja = "Checkbook Planilla"; tabla = "tPlanilla";   m = "planilla.m";   d = "Checkbook de planilla: posicion x concepto x mes" },
  @{ q = "CheckbookOpex";     hoja = "Checkbook OPEX";     tabla = "tOpex";       m = "opex.m";       d = "Checkbook de OPEX: depto x cuenta x detalle x mes (USD)" },
  @{ q = "CheckbookCostos";   hoja = "Checkbook Costos";   tabla = "tCostos";     m = "costos.m";     d = "Checkbook de costo de ventas (clase 5): depto x cuenta x mes (USD)" },
  @{ q = "Estadisticas";      hoja = "Estadisticas Rooms"; tabla = "tEstadisticas"; m = "estadisticas.m"; d = "Estadisticas de habitaciones por mes: disponibles, ocupadas, ocupacion, ADR, RevPAR" }
)
if ($Solo.Count -gt 0) { $defs = @($defs | Where-Object { $Solo -contains $_.q }) }
$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false; $xl.Visible = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $wb.Queries.FastCombine = $true
  foreach ($x in $defs) {
    $m = Get-Content -Raw -Encoding UTF8 (Join-Path $here $x.m)
    foreach ($q in @($wb.Queries)) { if ($q.Name -eq $x.q) { $q.Delete() } }
    foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $x.hoja) { $s.Delete() } }
    $wb.Queries.Add($x.q, $m, $x.d) | Out-Null
    $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count))
    $ws.Name = $x.hoja
    $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$($x.q);Extended Properties=`"`""
    $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
    $lo.Name = $x.tabla
    $qt = $lo.QueryTable
    $qt.CommandType = 2
    $qt.CommandText = "SELECT * FROM [$($x.q)]"
    $qt.BackgroundQuery = $false
    $qt.RefreshStyle = 0
    $qt.PreserveColumnInfo = $true
    $qt.AdjustColumnWidth = $true
    if ($Refrescar) {
      $qt.Refresh($false) | Out-Null
      foreach ($c in $lo.ListColumns) {
        if ($c.Name -match '^(M\d\d|Annual|Anio|Costo|Salario|Devengado|Cargas|Beneficios)') { $c.DataBodyRange.NumberFormat = '#,##0.00;[Red](#,##0.00);"-"' }
        elseif ($c.Name -match '^FTE') { $c.DataBodyRange.NumberFormat = '0.00' }
      }
      "{0,-20} filas = {1}" -f $x.hoja, $lo.ListRows.Count
    }
    $ws.Activate(); $xl.ActiveWindow.SplitRow = 1; $xl.ActiveWindow.FreezePanes = $true
  }
  $wb.Worksheets.Item("Config").Activate()
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
