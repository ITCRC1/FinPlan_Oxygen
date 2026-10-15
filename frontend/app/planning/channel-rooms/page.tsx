"use client";
/**
 * Planning → Channel Rooms Calculation.
 *
 * Owner, 2026-10-15: *«me gustaría que hagas otro tab para cálculo de rooms
 * revenue… en un sub tab en planning llamado Channel Rooms Calculation, y en
 * sub tab metas todos los tabs que se necesiten para poder llegar al número
 * final ya todo organizado… hay que dejar editable los drivers que activan los
 * cálculos»* · *«que funcione bien y después conectarlo»*.
 *
 * ## Por qué existe
 *
 * El modelo que hay saca Rooms de `rack por tipo de habitación × ocupación ×
 * factor de canal`, y eso necesita historia POR TIPO DE HABITACIÓN para
 * calibrarse. Oxygen no la tiene y no la va a tener hacia atrás. El modelo por
 * canal pide lo que el PMS sí sabe dar: noches y tarifa promedio por segmento
 * de venta, que es como lo propone Sales & Marketing.
 *
 * ## Los cuatro pasos, en orden
 *
 *     1 · Segmentos     se digita: noches y tarifa por segmento y mes
 *     2 · Estadísticas  sale: ingreso, ADR, ocupación, RevPAR mes a mes
 *     3 · Mix           sale: qué parte del ingreso trae cada canal
 *     4 · Conexión      el interruptor hacia el P&L
 *
 * Son sub-tabs y no pantallas sueltas porque el número final no se entiende sin
 * el camino: el ADR de la pantalla 2 sale de lo que se digitó en la 1.
 *
 * ## ⚠️ Nada llega al P&L hasta el paso 4
 *
 * Mientras `rooms_source` siga en `tarifas`, esto se llena y se compara sin
 * mover un número del reporte. Conectarlo es un acto aparte y explícito.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePlanningScenarioConUrl } from "@/lib/planningScenario";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { manejarPegado, repartirPegado, numeroDeExcel } from "@/lib/pegarGrilla";
import {
  getScenarios, getCanalRooms, saveCanalRooms, conectarCanalRooms,
  importarCanalRooms, versionesDelLibro,
  type Scenario, type CanalRoomsResponse,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import InputMoneda from "@/components/InputMoneda";
import Monto from "@/components/Monto";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const PASOS = ["segmentos", "estadisticas", "mix", "conexion"] as const;
type Paso = typeof PASOS[number];

const n = (v: string | number | undefined) => {
  const x = parseFloat(String(v ?? "").replace(/[, %$]/g, ""));
  return isNaN(x) ? 0 : x;
};
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD",
                              minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ent = (v: number) => Math.round(v).toLocaleString("en-US");
const pct = (v: number) => (v * 100).toFixed(1) + "%";

const btn = (on: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: on ? "pointer" : "not-allowed", border: "none",
  background: on ? "var(--brand)" : "var(--bg-surface)",
  color: on ? "#fff" : "var(--text-disabled)",
});
const inpNum: React.CSSProperties = {
  width: 72, textAlign: "right", padding: "3px 5px", fontSize: 12.5,
  borderRadius: 4, border: "1px solid var(--border-medium)",
  background: "var(--bg-base)", color: "var(--text-primary)",
  fontVariantNumeric: "tabular-nums",
};
const TD: React.CSSProperties = { padding: "4px 7px", textAlign: "right",
                                  fontVariantNumeric: "tabular-nums" };
const TH: React.CSSProperties = { ...TD, fontWeight: 600, fontSize: 11.5,
                                  color: "var(--text-secondary)" };

export default function ChannelRoomsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("channelRooms");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [data, setData] = useState<CanalRoomsResponse | null>(null);
  const [paso, setPaso] = useState<Paso>("segmentos");

  /** {code: {mes: {noches, tarifa}}} como texto, para escribir sin pelear. */
  const [vals, setVals] = useState<Record<string, Record<number, { noches: string; tarifa: string }>>>({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Importación
  const [archivo, setArchivo] = useState<File | null>(null);
  const [versiones, setVersiones] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [previo, setPrevio] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        if (!scenarioId) setScenarioId(elegir(all, "budget")?.id ?? all[0]?.id ?? "");
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cargar = useCallback(async (sid: string) => {
    setLoading(true); setError(null);
    try {
      const d = await getCanalRooms(sid);
      setData(d);
      const v: typeof vals = {};
      for (const s of d.segmentos) {
        v[s.code] = {};
        for (let m = 1; m <= 12; m++) v[s.code][m] = { noches: "0", tarifa: "0" };
      }
      for (const e of d.entradas) {
        if (!v[e.segmento_code]) continue;
        v[e.segmento_code][e.month] = { noches: String(n(e.noches)),
                                        tarifa: String(n(e.tarifa)) };
      }
      setVals(v); setDirty(false); setPrevio(null);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [tc]);

  useEffect(() => { if (scenarioId) cargar(scenarioId); }, [scenarioId, cargar]);

  const bloqueado = !!data?.locked;
  const segs = data?.segmentos ?? [];

  // ── El MISMO cálculo que el backend, para que el número se mueva al escribir.
  //    El que manda es el del servidor: al guardar se repinta con su respuesta.
  const calc = useMemo(() => {
    const porMes = MONTHS.map((_m, i) => {
      const mes = i + 1;
      const disp = n(data?.meses?.[i]?.disponibles);
      let nIng = 0, nTot = 0, ing = 0;
      const seg: Record<string, { noches: number; ingreso: number }> = {};
      for (const s of segs) {
        const c = vals[s.code]?.[mes];
        const noches = n(c?.noches), tarifa = n(c?.tarifa);
        const i2 = noches * tarifa;
        nTot += noches; ing += i2;
        if (s.genera_ingreso) nIng += noches;
        seg[s.code] = { noches, ingreso: i2 };
      }
      return { mes, disp, nIng, nTot, ing, seg,
               ocup: disp ? nIng / disp : 0, ocupTot: disp ? nTot / disp : 0,
               adr: nIng ? ing / nIng : 0, revpar: disp ? ing / disp : 0 };
    });
    const S = (f: (x: typeof porMes[0]) => number) => porMes.reduce((a, x) => a + f(x), 0);
    const nIng = S(x => x.nIng), ing = S(x => x.ing), disp = S(x => x.disp);
    return { porMes, total: {
      disp, nIng, nTot: S(x => x.nTot), ing,
      ocup: disp ? nIng / disp : 0, adr: nIng ? ing / nIng : 0,
      revpar: disp ? ing / disp : 0 } };
  }, [vals, segs, data, MONTHS]);

  function set(code: string, mes: number, campo: "noches" | "tarifa", v: string) {
    setVals(p => ({ ...p, [code]: { ...p[code], [mes]: { ...p[code]?.[mes], [campo]: v } } }));
    setDirty(true);
  }

  /** Pegar desde Excel: un bloque de meses entra desde donde se soltó. */
  function pegar(code: string, campo: "noches" | "tarifa", mes: number, bloque: string[][]) {
    setVals(p => {
      const fila = { ...p[code] };
      repartirPegado(bloque, 0, mes - 1, 1, 12, (_f, c, valor) => {
        fila[c + 1] = { ...fila[c + 1], [campo]: String(numeroDeExcel(valor)) };
      });
      return { ...p, [code]: fila };
    });
    setDirty(true);
  }

  async function guardar() {
    if (!scenarioId) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      const cuerpo = segs.flatMap(s => MONTHS.map((_m, i) => ({
        segmento_code: s.code, month: i + 1,
        noches: n(vals[s.code]?.[i + 1]?.noches),
        tarifa: n(vals[s.code]?.[i + 1]?.tarifa),
        ingreso: 0, tarifa_digitada: true,
      })));
      setData(await saveCanalRooms(scenarioId, cuerpo));
      setDirty(false); setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function conectar(fuente: "tarifas" | "canales") {
    if (!scenarioId) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      await conectarCanalRooms(scenarioId, fuente);
      await cargar(scenarioId);
      setMsg(fuente === "canales" ? t("connected") : t("disconnected"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function recalcular() {
    if (!scenarioId) return;
    setRecalc(true); setError(null);
    try { await recalcularYContar(scenarioId); setMsg(t("recalculated")); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setRecalc(false); }
  }

  async function elegirArchivo(f: File | null) {
    setArchivo(f); setVersiones([]); setVersion(""); setPrevio(null);
    if (!f || !scenarioId) return;
    try { setVersiones((await versionesDelLibro(scenarioId, f)).versiones); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function importar(aplicar: boolean) {
    if (!scenarioId || !archivo || !version) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      const r = await importarCanalRooms(scenarioId, archivo, version, aplicar);
      setPrevio(r as Record<string, unknown>);
      if (aplicar) { await cargar(scenarioId); setMsg(t("imported")); }
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function bajarExcel() {
    const sel = scenarios.find(x => x.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const filas: FilaCuadro[] = [];
    for (const s of segs) {
      filas.push({ label: `${s.nombre} · ${t("nights")}`,
        valores: [...calc.porMes.map(x => x.seg[s.code]?.noches ?? 0),
                  calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.noches ?? 0), 0)] });
      filas.push({ label: `${s.nombre} · ${t("revenue")}`,
        valores: [...calc.porMes.map(x => x.seg[s.code]?.ingreso ?? 0),
                  calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.ingreso ?? 0), 0)] });
    }
    filas.push({ label: t("totalRevenue"), es_total: true,
      valores: [...calc.porMes.map(x => x.ing), calc.total.ing] });
    try {
      await bajarCuadros("Channel_Rooms", [{
        titulo: t("title"), subtitulo: esc, hoja: t("sheet"),
        columnas: [{ label: t("segment"), ancho: 34, formato: "texto" },
                   ...MONTHS.map(m => ({ label: m, ancho: 13, formato: "usd2" as const })),
                   { label: tc("total"), ancho: 15, formato: "usd2" as const }],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  // ───────────────────────────── vistas ─────────────────────────────
  const fila = (etiqueta: string, valores: number[], fmt: (v: number) => string,
                fuerte = false, tenue = false) => (
    <tr style={{ borderBottom: "1px solid var(--border-subtle)",
                 fontWeight: fuerte ? 700 : undefined }}>
      <td style={{ ...TD, textAlign: "left", minWidth: 210,
                   color: tenue ? "var(--text-secondary)" : undefined }}>{etiqueta}</td>
      {valores.map((v, i) => (
        <td key={i} style={{ ...TD, color: tenue ? "var(--text-secondary)" : undefined }}>
          <Monto>{fmt(v)}</Monto>
        </td>
      ))}
    </tr>
  );

  const vistaSegmentos = (
    <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
            <th style={{ ...TH, textAlign: "left", minWidth: 230 }}>{t("segment")}</th>
            {MONTHS.map(m => <th key={m} style={TH}>{m}</th>)}
            <th style={TH}>{tc("total")}</th>
          </tr>
        </thead>
        <tbody>
          {segs.map(s => {
            const tn = calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.noches ?? 0), 0);
            const ti = calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.ingreso ?? 0), 0);
            return (
              <>
                <tr key={s.code + "-h"} style={{ background: "var(--bg-surface)" }}>
                  <td colSpan={14} style={{ padding: "6px 8px", fontWeight: 700 }}>
                    {s.nombre}
                    {!s.genera_ingreso && (
                      <span title={t("noRevenueHint")}
                        style={{ marginLeft: 8, fontSize: 11, fontWeight: 400,
                                 color: "var(--warning, #F59E0B)" }}>
                        · {t("noRevenue")}
                      </span>
                    )}
                  </td>
                </tr>
                <tr key={s.code + "-n"} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...TD, textAlign: "left", paddingLeft: 20 }}>{t("nights")}</td>
                  {MONTHS.map((_m, i) => (
                    <td key={i} style={TD}>
                      <input className="fin-input mono" type="number" min={0}
                        value={vals[s.code]?.[i + 1]?.noches ?? "0"} disabled={bloqueado}
                        onChange={e => set(s.code, i + 1, "noches", e.target.value)}
                        onPaste={e => manejarPegado(e, b => pegar(s.code, "noches", i + 1, b))}
                        style={inpNum} />
                    </td>
                  ))}
                  <td style={{ ...TD, fontWeight: 700 }}>{ent(tn)}</td>
                </tr>
                <tr key={s.code + "-t"} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...TD, textAlign: "left", paddingLeft: 20 }}>{t("rate")}</td>
                  {MONTHS.map((_m, i) => (
                    <td key={i} style={TD}>
                      <InputMoneda value={vals[s.code]?.[i + 1]?.tarifa ?? "0"}
                        disabled={bloqueado}
                        onChange={v => set(s.code, i + 1, "tarifa", v)}
                        onPaste={e => manejarPegado(e, b => pegar(s.code, "tarifa", i + 1, b))}
                        style={{ minWidth: 92, fontSize: 12.5, padding: "3px 4px" }} />
                    </td>
                  ))}
                  <td style={{ ...TD, fontWeight: 700 }}>
                    <Monto>{usd(tn ? ti / tn : 0)}</Monto>
                  </td>
                </tr>
                <tr key={s.code + "-i"} style={{ borderBottom: "1px solid var(--border-subtle)",
                                                 color: "var(--text-secondary)" }}>
                  <td style={{ ...TD, textAlign: "left", paddingLeft: 20 }}>{t("revenue")}</td>
                  {calc.porMes.map((x, i) => (
                    <td key={i} style={TD}><Monto>{usd(x.seg[s.code]?.ingreso ?? 0)}</Monto></td>
                  ))}
                  <td style={{ ...TD, fontWeight: 700 }}><Monto>{usd(ti)}</Monto></td>
                </tr>
              </>
            );
          })}
          <tr style={{ borderTop: "2px solid var(--border-medium)" }}>
            <td colSpan={14} style={{ padding: "6px 8px", fontWeight: 700 }}>{tc("total")}</td>
          </tr>
          {fila(t("nightsRevenue"), [...calc.porMes.map(x => x.nIng), calc.total.nIng], ent, true)}
          {fila(t("nightsAll"), [...calc.porMes.map(x => x.nTot), calc.total.nTot], ent, false, true)}
          {fila(t("totalRevenue"), [...calc.porMes.map(x => x.ing), calc.total.ing], usd, true)}
        </tbody>
      </table>
    </div>
  );

  const vistaEstadisticas = (
    <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
            <th style={{ ...TH, textAlign: "left", minWidth: 230 }}>{t("metric")}</th>
            {MONTHS.map(m => <th key={m} style={TH}>{m}</th>)}
            <th style={TH}>{tc("total")}</th>
          </tr>
        </thead>
        <tbody>
          {fila(t("totalRevenue"), [...calc.porMes.map(x => x.ing), calc.total.ing], usd, true)}
          {fila(t("nightsRevenue"), [...calc.porMes.map(x => x.nIng), calc.total.nIng], ent)}
          {fila(t("adr"), [...calc.porMes.map(x => x.adr), calc.total.adr], usd, true)}
          {fila(t("occupancy"), [...calc.porMes.map(x => x.ocup), calc.total.ocup], pct)}
          {fila(t("occupancyAll"), [...calc.porMes.map(x => x.ocupTot),
                                    calc.total.disp ? calc.total.nTot / calc.total.disp : 0],
                pct, false, true)}
          {fila(t("revpar"), [...calc.porMes.map(x => x.revpar), calc.total.revpar], usd, true)}
          {fila(t("available"), [...calc.porMes.map(x => x.disp), calc.total.disp], ent, false, true)}
        </tbody>
      </table>
    </div>
  );

  const vistaMix = (
    <table style={{ width: "100%", maxWidth: 680, borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
          <th style={{ ...TH, textAlign: "left" }}>{t("segment")}</th>
          <th style={TH}>{t("nights")}</th>
          <th style={TH}>{t("revenue")}</th>
          <th style={TH}>{t("rate")}</th>
          <th style={TH}>{t("mix")}</th>
        </tr>
      </thead>
      <tbody>
        {segs.map(s => {
          const tn = calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.noches ?? 0), 0);
          const ti = calc.porMes.reduce((a, x) => a + (x.seg[s.code]?.ingreso ?? 0), 0);
          return (
            <tr key={s.code} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <td style={{ ...TD, textAlign: "left" }}>{s.nombre}</td>
              <td style={TD}>{ent(tn)}</td>
              <td style={TD}><Monto>{usd(ti)}</Monto></td>
              <td style={TD}><Monto>{usd(tn ? ti / tn : 0)}</Monto></td>
              <td style={TD}>{calc.total.ing ? pct(ti / calc.total.ing) : "—"}</td>
            </tr>
          );
        })}
        <tr style={{ borderTop: "2px solid var(--border-medium)", fontWeight: 700 }}>
          <td style={{ ...TD, textAlign: "left" }}>{tc("total")}</td>
          <td style={TD}>{ent(calc.total.nTot)}</td>
          <td style={TD}><Monto>{usd(calc.total.ing)}</Monto></td>
          <td style={TD}><Monto>{usd(calc.total.adr)}</Monto></td>
          <td style={TD}>100.0%</td>
        </tr>
      </tbody>
    </table>
  );

  const vistaConexion = (
    <div style={{ maxWidth: 720 }}>
      <div style={{ padding: "12px 14px", marginBottom: 16, borderRadius: 8,
        border: "1px solid var(--border-medium)", background: "var(--bg-surface)" }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>
          {data?.conectado ? t("connectedTitle") : t("notConnectedTitle")}
        </div>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>
          {data?.conectado ? t("connectedBody") : t("notConnectedBody")}
        </p>
      </div>
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <button onClick={() => conectar("canales")}
          disabled={saving || bloqueado || !!data?.conectado}
          style={btn(!saving && !bloqueado && !data?.conectado)}>
          {t("connect")}
        </button>
        <button onClick={() => conectar("tarifas")}
          disabled={saving || bloqueado || !data?.conectado}
          style={btn(!saving && !bloqueado && !!data?.conectado)}>
          {t("disconnect")}
        </button>
      </div>

      <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{t("importTitle")}</h3>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 10 }}>
        {t("importBody")}
      </p>
      <input type="file" accept=".xlsx" disabled={bloqueado}
        onChange={e => elegirArchivo(e.target.files?.[0] ?? null)}
        style={{ fontSize: 13, marginBottom: 10 }} />
      {versiones.length > 0 && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
                      marginBottom: 12 }}>
          <select className="fin-input" value={version}
            onChange={e => { setVersion(e.target.value); setPrevio(null); }}
            style={{ padding: "6px 10px", fontSize: 13, minWidth: 220 }}>
            <option value="">{t("pickVersion")}</option>
            {versiones.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
          <button onClick={() => importar(false)} disabled={!version || saving}
            style={btn(!!version && !saving)}>{t("preview")}</button>
          <button onClick={() => importar(true)} disabled={!previo || saving}
            style={btn(!!previo && !saving)}>{t("apply")}</button>
        </div>
      )}
      {previo && (
        <div style={{ padding: "10px 12px", borderRadius: 6, fontSize: 13,
          background: "var(--bg-surface)", border: "1px solid var(--border-medium)" }}>
          <div>{t("previewFound", {
            celdas: String(previo.celdas ?? ""), meses: String((previo.meses as number[])?.length ?? 0),
          })}</div>
          <div style={{ marginTop: 4 }}>
            {t("nights")}: <b>{ent(n(previo.noches as string))}</b> ·{" "}
            {t("revenue")}: <b><Monto>{usd(n(previo.ingreso as string))}</Monto></b>
          </div>
          {Array.isArray(previo.desconocidos) && previo.desconocidos.length > 0 && (
            <div style={{ marginTop: 6, color: "var(--warning, #F59E0B)" }}>
              ⚠️ {t("unknownSegments")}: {(previo.desconocidos as string[]).join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 24px" }}>
      <IrA esc={scenarioId} />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("title")}</h1>
      <p style={{ maxWidth: "92ch", fontSize: 13, color: "var(--text-secondary)",
                  marginBottom: 14 }}>{t("intro")}</p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12,
                    flexWrap: "wrap" }}>
        <select className="fin-input" value={scenarioId}
          onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "6px 10px", fontSize: 13, minWidth: 230, fontWeight: 600 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>
          ))}
        </select>
        {data && (
          <span style={{ fontSize: 12, padding: "3px 10px", borderRadius: 999,
            background: data.conectado ? "var(--positive, #26A69A)" : "var(--bg-surface)",
            color: data.conectado ? "#fff" : "var(--text-secondary)",
            border: data.conectado ? "none" : "1px solid var(--border-medium)" }}>
            {data.conectado ? t("badgeOn") : t("badgeOff")}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button onClick={guardar} disabled={!dirty || saving || bloqueado}
          style={btn(dirty && !saving && !bloqueado)}>
          {saving ? tc("saving") : tc("save")}
        </button>
        <button onClick={recalcular} disabled={recalc || bloqueado}
          style={btn(!recalc && !bloqueado)}>
          {recalc ? tc("recalc.running") : t("recalc")}
        </button>
        <button onClick={bajarExcel} disabled={loading}
          style={{ padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 6,
                   cursor: loading ? "default" : "pointer", background: "transparent",
                   color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border-medium)",
                    marginBottom: 14 }}>
        {PASOS.map((p, i) => (
          <button key={p} onClick={() => setPaso(p)}
            style={{ padding: "7px 14px", fontSize: 13, border: "none",
              background: "transparent", cursor: "pointer",
              fontWeight: paso === p ? 700 : 400,
              color: paso === p ? "var(--text-primary)" : "var(--text-secondary)",
              borderBottom: paso === p ? "2px solid var(--brand)" : "2px solid transparent" }}>
            {i + 1} · {t(`step_${p}`)}
          </button>
        ))}
      </div>

      {msg && <div style={{ color: "var(--positive, #26A69A)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? <div style={{ padding: 24 }}>{tc("loading")}</div> : (
        paso === "segmentos" ? vistaSegmentos
        : paso === "estadisticas" ? vistaEstadisticas
        : paso === "mix" ? vistaMix
        : vistaConexion
      )}
    </div>
  );
}
