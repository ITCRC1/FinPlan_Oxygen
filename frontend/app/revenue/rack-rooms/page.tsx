"use client";
/**
 * Planning → Rack Rooms Calculation.
 *
 * Owner, 2026-10-16: *«me interesa clonar el tab KPIs RACK y el tab Origen
 * Tarifa Rac y la base de datos viene desde el tab llamado Resumen Mensual.
 * Favor crea un modelo donde yo pueda modificar las variables inputs y que
 * derive todo lo demás»*.
 *
 * ## Los seis sub-tabs, en el orden del cálculo
 *
 *     1 · Villas y RAC    se digita: unidades y tarifa por temporada
 *     2 · Temporadas      se digita: los rangos de fecha del año
 *     3 · Noches          se digita: noches por segmento y mes
 *     4 · Origen tarifa   sale: días por temporada → RAC del mes → tarifa neta
 *     5 · KPIs Rack       sale: ingreso, ADR, ocupación, RevPAR mes a mes
 *     6 · Conexión        el interruptor hacia el P&L
 *
 * Son sub-tabs y no pantallas sueltas porque el número final no se entiende sin
 * el camino: el ADR del 5 sale del RAC del 4, que sale de lo que se digitó en
 * el 1 y el 2.
 *
 * ## ⚠️ Nada llega al P&L hasta el paso 6
 *
 * Mientras `rooms_source` siga en `tarifas`, esto se llena y se compara sin
 * mover un número del reporte. Conectarlo es un acto aparte y explícito.
 *
 * ## ⚠️ Los CONTROLES se muestran, no se esconden
 *
 * El libro del owner tiene filas de control que tienen que dar cero: días sin
 * temporada, unidades que no coinciden, segmentos sin comisión. Cuando fallan,
 * el total **sigue cuadrando consigo mismo** — por eso van arriba y en rojo, no
 * enterrados en una celda que nadie mira.
 */
import React from "react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import IrA from "@/components/IrA";
import {
  getScenarios, getRackRooms, saveRackVillas, saveRackTemporadas,
  saveRackComisiones, saveRackNoches, conectarRackRooms,
  previewRackRooms, bajarPlantillaRack, subirPlantillaRack,
  type CambioPlantilla, type RechazoPlantilla,
  type Scenario, type RackRoomsResponse, type RackVillaFila,
  type RackTemporadaFila, type RackComisionFila, type RackMes,
} from "@/lib/api";
import { elegir } from "@/lib/escenarioPreferido";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { fmtUsd, fmtPct, fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { manejarPegado, numeroDeExcel, repartirPegado } from "@/lib/pegarGrilla";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { recalcularYContar } from "@/lib/recalcular";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const PASOS = ["villas", "temporadas", "noches", "origen", "kpis", "conexion"] as const;
type Paso = typeof PASOS[number];
const TEMPORADAS = ["PICO", "ALTA", "VERDE"] as const;

/** Texto → número tolerante: acepta lo que sale de Excel (`$1,234.50`, `20%`). */
const n = (v: string | number | undefined | null) => {
  const x = parseFloat(String(v ?? "").replace(/[, %$]/g, ""));
  return isNaN(x) ? 0 : x;
};

const btn = (on: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: on ? "pointer" : "not-allowed", border: "none",
  background: on ? "var(--brand)" : "var(--bg-surface)",
  color: on ? "#fff" : "var(--text-disabled)",
});
const excelBtn: React.CSSProperties = {
  padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 5,
  cursor: "pointer", background: "transparent", color: "var(--positive)",
  border: "1px solid var(--positive)",
};
const inpNum: React.CSSProperties = {
  width: 78, textAlign: "right", padding: "3px 5px", fontSize: 12.5,
  borderRadius: 4, border: "1px solid var(--border-medium)",
  background: "var(--bg-base)", color: "var(--text-primary)",
  fontVariantNumeric: "tabular-nums",
};
const TD: React.CSSProperties = { padding: "4px 7px", textAlign: "right",
                                  fontVariantNumeric: "tabular-nums" };
const TDL: React.CSSProperties = { padding: "4px 7px", textAlign: "left" };
const BLQ: React.CSSProperties = {
  ...TDL, fontWeight: 700, paddingTop: 12, fontSize: 11.5,
  letterSpacing: 0.4, textTransform: "uppercase",
  color: "var(--text-secondary)",
};
const AVISO: React.CSSProperties = {
  padding: "8px 12px", borderRadius: 5, fontSize: 12.5, marginBottom: 10,
  background: "var(--bg-surface)", borderLeft: "3px solid var(--negative)",
  color: "var(--text-primary)",
};

export default function RackRoomsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("rackRooms");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [data, setData] = useState<RackRoomsResponse | null>(null);
  const [paso, setPaso] = useState<Paso>("villas");

  // Los inputs se editan como TEXTO y se convierten al guardar: un `number`
  // controlado no deja escribir «0.», ni borrar el campo para teclear otra cosa.
  const [villas, setVillas] = useState<RackVillaFila[]>([]);
  const [temps, setTemps] = useState<RackTemporadaFila[]>([]);
  const [coms, setComs] = useState<Record<string, Record<number, string>>>({});
  const [propiaDe, setPropiaDe] = useState<Record<string, boolean>>({});
  const [noches, setNoches] = useState<Record<string, Record<number, string>>>({});
  const [tarifasPropias, setTarifasPropias] = useState<Record<string, Record<number, string>>>({});

  /** Hay cambios sin guardar: lo que se ve es la previsualización. */
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const aplicar2 = useCallback((d: RackRoomsResponse) => {
    setData(d);
    setVillas(d.villas.map(v => ({ ...v })));
    setTemps(d.temporadas.map(x => ({ ...x })));
    // Un segmento sin fila de comisión se muestra en 0% — que es como lo lee el
    // motor: sin fila se vende A RACK, no gratis. Ver `tarifa_del_segmento`.
    // {code: {mes: '0.25'}} — doce por segmento, como texto para poder
    // escribir «0.» sin que el campo se pelee.
    const cc: Record<string, Record<number, string>> = {};
    const propia: Record<string, boolean> = {};
    for (const s of d.segmentos) { cc[s.code] = {}; propia[s.code] = false; }
    for (const c of d.comisiones) {
      (cc[c.segmento_code] ??= {})[c.month ?? 1] = String(n(c.comision_pct));
      if (c.tarifa_propia) propia[c.segmento_code] = true;
    }
    setComs(cc);
    setPropiaDe(propia);
    const nn: Record<string, Record<number, string>> = {};
    const tp: Record<string, Record<number, string>> = {};
    for (const s of d.segmentos) { nn[s.code] = {}; tp[s.code] = {}; }
    for (const e of d.entradas) {
      (nn[e.segmento_code] ??= {})[e.month] = String(n(e.noches));
      (tp[e.segmento_code] ??= {})[e.month] = String(n(e.tarifa));
    }
    setNoches(nn);
    setTarifasPropias(tp);
    setDirty(false);
    setPrevio(null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setError(null);
    try { aplicar2(await getRackRooms(sid)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [aplicar2]);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const locked = !!data?.locked;
  const segs = data?.segmentos ?? [];
  const propias = useMemo(
    () => new Set(Object.entries(propiaDe).filter(([, v]) => v).map(([k]) => k)),
    [propiaDe]);

  /** Lo que se manda al guardar: una fila por segmento y mes. */
  const comisionesAEnviar = useCallback((): RackComisionFila[] =>
    segs.flatMap(s => MONTHS.map((_, mi) => ({
      segmento_code: s.code, month: mi + 1,
      comision_pct: String(n(coms[s.code]?.[mi + 1])),
      tarifa_propia: !!propiaDe[s.code],
    }))), [segs, coms, propiaDe]);

  /** ¿Este segmento tiene algún mes distinto a enero? Se muestra al lado del
   *  campo de enero: sin eso, cambiar enero parecería no haber hecho nada en
   *  los meses que alguien había ajustado a mano. */
  const mesesDistintos = useCallback((code: string) => {
    const ene = n(coms[code]?.[1]);
    return MONTHS.map((_, mi) => mi + 1).filter(
      m => m > 1 && n(coms[code]?.[m]) !== ene);
  }, [coms]);

  // ── Pegar desde Excel ──────────────────────────────────────────────────────
  //
  // El owner arma esto en un libro y lo trae pegado. Sin esto los doce meses
  // entran DENTRO de la primera celda: no falla, no avisa, y hay que teclearlos
  // de nuevo. Owner, 2026-10-04: *«rate y todo queda en la primera celda»*.

  /** La grilla de noches: filas = segmentos (en pantalla), columnas = meses. */
  const pegarNoches = useCallback((fi: number, mi: number, bloque: string[][]) => {
    setNoches(v => {
      const out = { ...v };
      repartirPegado(bloque, fi, mi, segs.length, 12, (f, c, valor) => {
        const code = segs[f].code;
        out[code] = { ...(out[code] ?? {}), [c + 1]: String(numeroDeExcel(valor)) };
      });
      return out;
    });
  }, [segs]);

  /** Las tarifas propias: sólo las filas que tienen tarifa propia. */
  const conTarifaPropia = useMemo(
    () => segs.filter(s => propias.has(s.code)), [segs, propias]);
  const pegarTarifas = useCallback((fi: number, mi: number, bloque: string[][]) => {
    setTarifasPropias(v => {
      const out = { ...v };
      repartirPegado(bloque, fi, mi, conTarifaPropia.length, 12, (f, c, valor) => {
        const code = conTarifaPropia[f].code;
        out[code] = { ...(out[code] ?? {}), [c + 1]: String(numeroDeExcel(valor)) };
      });
      return out;
    });
  }, [conTarifaPropia]);

  /** El cuadro de villas: columnas = unidades, RAC pico, alta, verde. */
  const COLS_VILLA = ["unidades", "rac_pico", "rac_alta", "rac_verde"] as const;
  const pegarVillas = useCallback((fi: number, ci: number, bloque: string[][]) => {
    setVillas(xs => {
      const out = xs.map(x => ({ ...x }));
      repartirPegado(bloque, fi, ci, out.length, COLS_VILLA.length, (f, c, valor) => {
        const k = COLS_VILLA[c];
        const num = numeroDeExcel(valor);
        // Unidades es un entero: un «2.5» pegado por error se trunca acá y no
        // en el backend, donde el redondeo no se vería.
        (out[f] as Record<string, unknown>)[k] =
          k === "unidades" ? Math.max(0, Math.round(num)) : String(num);
      });
      return out;
    });
  }, []);

  /** Guarda y recarga. El backend devuelve el cuadro recalculado entero. */
  async function guardar(fn: () => Promise<RackRoomsResponse>) {
    if (!scenarioId || locked) return;
    setSaving(true); setError(null); setMsg(null);
    try { aplicar2(await fn()); setMsg(t("saved")); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function recalcular() {
    if (!scenarioId) return;
    setRecalc(true); setError(null);
    try {
      await recalcularYContar(scenarioId);
      await load(scenarioId);
      setMsg(t("recalculated"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setRecalc(false); }
  }

  // ── La plantilla de Excel ─────────────────────────────────────────────────
  //
  // Owner, 2026-10-16: *«por qué no creás un download file para actualizar los
  // datos vía upload»*. Hay trabajo que se hace mejor en Excel —arrastrar una
  // celda, comparar meses de corrido, revisarlo con alguien antes de subirlo—
  // que celda por celda acá.
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cambios, setCambios] = useState<CambioPlantilla[] | null>(null);
  const [rechazos, setRechazos] = useState<RechazoPlantilla[]>([]);
  const [subiendo, setSubiendo] = useState(false);

  async function bajar() {
    const sel = scenarios.find(x => x.id === scenarioId);
    const nombre = `Rooms_por_segmento_${sel?.year ?? ""}.xlsx`;
    try { await bajarPlantillaRack(scenarioId, nombre); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  /** `aplicar = false` sólo REVISA. Lo que se escribe, se escribe después de
   *  que alguien miró la lista. */
  async function subir(aplicar: boolean) {
    if (!archivo || !scenarioId) return;
    setSubiendo(true); setError(null); setMsg(null);
    try {
      const r = await subirPlantillaRack(scenarioId, archivo, aplicar);
      setCambios(r.cambios);
      setRechazos(r.rechazos);
      if (r.aplicado) {
        if (r.cuadro) aplicar2(r.cuadro);
        setArchivo(null);
        setCambios(null);
        setMsg(t("uploadApplied", { n: r.cambios.length }));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setSubiendo(false); }
  }

  // ── La previsualización ───────────────────────────────────────────────────
  //
  // Owner, 2026-10-16: *«si me cambian una variable, éste debería ser el punto
  // donde se cambie y todo lo demás debe actualizarse o derivarse»*.
  //
  // ⚠️ El cuadro derivado NO se calcula acá. Se le pide al servidor, que corre
  // el mismo `_armar` del `GET`. Derivar en el navegador sería más rápido y
  // tendría la fórmula escrita dos veces: el día que cambie el redondeo, una
  // se corrige y la otra no — y lo que se ve deja de ser lo que se guarda.
  const [previo, setPrevio] = useState<RackRoomsResponse | null>(null);
  const [calculando, setCalculando] = useState(false);

  /** Lo tecleado, en la forma que espera la puerta. */
  const loTecleado = useCallback(() => segs.flatMap(s => MONTHS.map((_, mi) => ({
    segmento_code: s.code, month: mi + 1,
    noches: n(noches[s.code]?.[mi + 1]),
    ...(propias.has(s.code)
      ? { tarifa: n(tarifasPropias[s.code]?.[mi + 1]) } : {}),
  }))), [segs, noches, tarifasPropias, propias]);

  useEffect(() => {
    if (!dirty || !scenarioId) return;
    // Se espera a que deje de teclear: una llamada por tecla haría ochenta
    // viajes para escribir «150».
    const id = setTimeout(async () => {
      setCalculando(true);
      try { setPrevio(await previewRackRooms(scenarioId, loTecleado(),
                                             comisionesAEnviar())); }
      catch { /* el cuadro se queda como estaba; el error sale al guardar */ }
      finally { setCalculando(false); }
    }, 600);
    return () => clearTimeout(id);
  }, [dirty, scenarioId, loTecleado, comisionesAEnviar]);

  /** Lo que se MUESTRA: la previsualización si hay cambios, si no lo guardado. */
  const vista = (dirty && previo) ? previo : data;

  async function guardarEntrada() {
    await guardar(async () => {
      // Las comisiones primero: la tarifa sale de ellas, así que guardar las
      // noches antes las derivaría con la comisión vieja.
      await saveRackComisiones(scenarioId, comisionesAEnviar());
      return saveRackNoches(scenarioId, loTecleado());
    });
    setDirty(false);
    setPrevio(null);
  }

  /** Una fila del cuadro: doce meses + total, con su formato.
   *
   * El cuadro tiene veinte filas de la misma forma. Escritas a mano una por
   * una es donde se cuela la que apunta a la columna de al lado — y una fila
   * corrida no falla, sólo muestra otro número.
   */
  const ms = data?.meses ?? [];
  const vm = vista?.meses ?? [];
  const Fila = ({ l, v, t: tot, f, bold, sub, hint }: {
    l: string; v: (m: RackMes) => number; t: number;
    f: (x: number) => string; bold?: boolean; sub?: boolean; hint?: string;
  }) => (
    <tr>
      <td style={{ ...TDL, fontWeight: bold ? 700 : undefined,
                   paddingLeft: sub ? 22 : undefined,
                   color: sub ? "var(--text-secondary)" : undefined }}
          title={hint}>
        {sub ? "↳ " : ""}{l}
      </td>
      {ms.map(m => (
        <td key={m.month} style={{ ...TD, fontWeight: bold ? 700 : undefined }}>
          {f(v(m))}
        </td>))}
      <td style={{ ...TD, fontWeight: 700 }}>{f(tot)}</td>
    </tr>
  );

  /** Una fila DERIVADA, pegada a la que se edita. Gris y sin caja: lo que no
   *  se puede escribir no se tiene que ver escribible. */
  const Der = ({ l, v, f, t: tot }: {
    l: string; v: (m: RackMes) => number; f: (x: number) => string; t?: number;
  }) => (
    <tr>
      <td style={{ ...TDL, paddingLeft: 20, color: "var(--text-secondary)",
                   fontSize: 12 }}>{l}</td>
      <td />
      {vm.map(m => (
        <td key={m.month} style={{ ...TD, color: "var(--text-secondary)" }}>
          {f(v(m))}
        </td>))}
      <td style={{ ...TD, color: "var(--text-secondary)" }}>
        {tot === undefined ? "" : f(tot)}
      </td>
    </tr>
  );

  /** Una fila del bloque de TOTALES. Lleva la columna de comisión vacía. */
  const Tot = ({ l, v, t: tot, f, bold, hint }: {
    l: string; v: (m: RackMes) => number; t: number;
    f: (x: number) => string; bold?: boolean; hint?: string;
  }) => (
    <tr>
      <td style={{ ...TDL, fontWeight: bold ? 700 : undefined }} title={hint}>{l}</td>
      <td />
      {vm.map(m => (
        <td key={m.month} style={{ ...TD, fontWeight: bold ? 700 : undefined }}>
          {f(v(m))}
        </td>))}
      <td style={{ ...TD, fontWeight: 700 }}>{f(tot)}</td>
    </tr>
  );

  // ── Los controles del libro ────────────────────────────────────────────────
  const avisos: string[] = [];
  if (data && !data.hay_tarifario) avisos.push(t("warnNoTariff"));
  if (data && !data.controles.unidades.coinciden) {
    avisos.push(t("warnUnits", { hotel: data.controles.unidades.hotel,
                                 tarifario: data.controles.unidades.tarifario }));
  }
  if (data?.controles.meses_sin_temporada.length) {
    avisos.push(t("warnSeasonGap", {
      meses: data.controles.meses_sin_temporada.map(m => MONTHS[m - 1]).join(", ") }));
  }
  if (data?.controles.segmentos_sin_comision.length) {
    avisos.push(t("warnNoCommission", {
      codes: data.controles.segmentos_sin_comision.join(", ") }));
  }

  // ── Excel: el cuadro de KPIs, que es el que se manda afuera ────────────────
  async function bajarExcel() {
    if (!data) return;
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const d = data;
    const fila = (label: string, pick: (m: typeof d.meses[0]) => number,
                  formato: FilaCuadro["formato"], total: number,
                  nivel = 1): FilaCuadro =>
      ({ label, nivel, formato, valores: [...d.meses.map(pick), total] });
    const T = d.total;
    const bloque = (label: string): FilaCuadro =>
      ({ label, es_total: true, valores: Array(13).fill(null) });
    const R = T.rack;
    // El mismo orden que la pestaña `KPIs Rack` del libro, bloque por bloque.
    // ⚠️ El rack va JUNTO con el neto: el neto es lo que entra al P&L y el rack
    // es contra lo que se mide el descuento del canal.
    const filas: FilaCuadro[] = [
      bloque(t("blockCapacity")),
      fila(t("available"), m => n(m.disponibles), "num", n(T.disponibles)),
      fila(t("nightsRevenue"), m => n(m.rack.noches_facturadas), "num",
           n(R.noches_facturadas)),
      fila(t("nightsOwnRate"), m => n(m.rack.noches_tarifa_propia), "num",
           n(R.noches_tarifa_propia)),
      fila(t("nightsComp"), m => n(m.rack.noches_cortesia), "num",
           n(R.noches_cortesia)),
      fila(t("occupancy"), m => n(m.ocupacion), "pct", n(T.ocupacion)),
      fila(t("occupancyTotal"), m => n(m.ocupacion_total), "pct", n(T.ocupacion_total)),
      bloque(t("blockRackRate")),
      fila(t("racWeighted"), m => n(m.rac_ponderado), "usd2",
           n(R.adr_rack_sin_propias)),
      bloque(t("blockRackRevenue")),
    ];
    for (const s of segs.filter(x => x.genera_ingreso)) {
      filas.push({
        label: s.nombre, nivel: 1, formato: "usd2",
        valores: [...d.meses.map(m => n(m.segmentos[s.code]?.ingreso_rack)),
                  d.meses.reduce((a, m) => a + n(m.segmentos[s.code]?.ingreso_rack), 0)],
      });
    }
    filas.push(
      fila(t("totalRackRevenue"), m => n(m.rack.ingreso_rack), "usd2",
           n(R.ingreso_rack)),
      bloque(t("blockRackKpis")),
      fila(t("adrRack"), m => n(m.rack.adr_rack), "usd2", n(R.adr_rack)),
      fila(t("adrRackNoOwn"), m => n(m.rack.adr_rack_sin_propias), "usd2",
           n(R.adr_rack_sin_propias)),
      fila(t("revparRack"), m => n(m.rack.revpar_rack), "usd2", n(R.revpar_rack)),
      bloque(t("blockRackVsNet")),
      fila(t("totalNetRevenue"), m => n(m.rack.ingreso_neto), "usd2",
           n(R.ingreso_neto)),
      fila(t("adrNet"), m => n(m.rack.adr_neto), "usd2", n(R.adr_neto)),
      fila(t("revparNet"), m => n(m.rack.revpar_neto), "usd2", n(R.revpar_neto)),
      fila(t("commissionUsd"), m => n(m.rack.comision_usd), "usd2",
           n(R.comision_usd)),
      fila(t("commissionPct"), m => n(m.rack.comision_pct), "pct",
           n(R.comision_pct)),
      fila(t("rackKept"), m => n(m.rack.pct_rack_retenido), "pct",
           n(R.pct_rack_retenido)),
      bloque(t("blockSegments")),
    );
    for (const s of segs) {
      filas.push({
        label: s.nombre, nivel: 1, formato: "usd2",
        valores: [...d.meses.map(m => n(m.segmentos[s.code]?.ingreso)),
                  n(T.segmentos[s.code]?.ingreso)],
      });
    }
    filas.push(bloque(t("blockRackMix")));
    for (const s of segs.filter(x => x.genera_ingreso)) {
      filas.push({
        label: s.nombre, nivel: 1, formato: "pct",
        valores: [...d.meses.map(m => n(m.mix_rack?.[s.code])),
                  n(T.mix_rack?.[s.code])],
      });
    }
    try {
      await bajarCuadros("Rack_Rooms", [{
        titulo: "Rack Rooms Calculation",
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Rack Rooms",
        columnas: [
          { label: t("concept"), ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 12, formato: "usd2" as const })),
          { label: tc("total"), ancho: 14, formato: "usd2" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Rack Rooms Calculation
        </h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
                className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>))}
        </select>
        <button onClick={bajarExcel} style={excelBtn}>⬇ Excel</button>
        {data?.conectado && (
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--positive)" }}>
            ● {t("connected")}
          </span>)}
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t("intro")}
      </p>

      {/* Los sub-tabs, en el orden del cálculo */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {PASOS.map((p, i) => (
          <button key={p} onClick={() => setPaso(p)} style={{
            ...btn(true),
            background: paso === p ? "var(--brand)" : "var(--bg-surface)",
            color: paso === p ? "#fff" : "var(--text-secondary)",
          }}>{i + 1} · {t(`step_${p}`)}</button>))}
      </div>

      {avisos.map((a, i) => <div key={i} style={AVISO}>⚠️ {a}</div>)}
      {error && <div style={{ ...AVISO, borderLeftColor: "var(--negative)" }}>{error}</div>}
      {msg && <div style={{ ...AVISO, borderLeftColor: "var(--positive)" }}>{msg}</div>}
      {locked && <div style={AVISO}>🔒 {t("lockedHint")}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : !data ? null : (
        <>
          {/* ── 1 · Villas y RAC ───────────────────────────────────────────── */}
          {paso === "villas" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("villasHint")}
              </p>
              <table className="fin-table" style={{ minWidth: 720 }}>
                <thead><tr>
                  <th style={{ textAlign: "left", minWidth: 200 }}>{t("villa")}</th>
                  <th style={{ textAlign: "right" }}>{t("units")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonPICO")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonALTA")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonVERDE")}</th>
                  <th />
                </tr></thead>
                <tbody>
                  {villas.map((v, i) => (
                    <tr key={i}>
                      <td style={TDL}>
                        <input value={v.villa} disabled={locked} className="fin-input"
                               style={{ width: 200, fontSize: 12.5 }}
                               onChange={e => setVillas(xs => xs.map((x, j) =>
                                 j === i ? { ...x, villa: e.target.value } : x))} />
                      </td>
                      {COLS_VILLA.map((k, ki) => (
                        <td key={k} style={TD}>
                          <input value={String(v[k] ?? "")} disabled={locked} style={inpNum}
                                 onPaste={e => manejarPegado(e, b => pegarVillas(i, ki, b))}
                                 onChange={e => setVillas(xs => xs.map((x, j) =>
                                   j === i ? { ...x, [k]: k === "unidades"
                                     ? Math.max(0, Math.round(n(e.target.value)))
                                     : e.target.value } : x))} />
                        </td>))}
                      <td style={TD}>
                        <button disabled={locked} style={{ ...btn(!locked), padding: "3px 9px" }}
                                onClick={() => setVillas(xs => xs.filter((_, j) => j !== i))}>
                          ✕
                        </button>
                      </td>
                    </tr>))}
                  <tr>
                    <td style={{ ...TDL, fontWeight: 700 }}>{tc("total")}</td>
                    <td style={{ ...TD, fontWeight: 700 }}>
                      {fmtInt(villas.reduce((a, v) => a + (v.unidades || 0), 0))}
                    </td>
                    <td colSpan={4} />
                  </tr>
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button disabled={locked} style={btn(!locked)}
                        onClick={() => setVillas(xs => [...xs, {
                          villa: "", unidades: 0, rac_pico: "0", rac_alta: "0",
                          rac_verde: "0", orden: xs.length }])}>
                  + {t("addVilla")}
                </button>
                <button disabled={locked || saving} style={btn(!locked && !saving)}
                        onClick={() => guardar(() => saveRackVillas(scenarioId,
                          villas.map((v, i) => ({ ...v, orden: i }))))}>
                  {saving ? tc("saving") : tc("save")}
                </button>
              </div>
            </div>)}

          {/* ── 2 · Temporadas ─────────────────────────────────────────────── */}
          {paso === "temporadas" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("seasonsHint")}
              </p>
              <table className="fin-table" style={{ minWidth: 560 }}>
                <thead><tr>
                  <th style={{ textAlign: "left" }}>{t("season")}</th>
                  <th style={{ textAlign: "left" }}>{t("from")}</th>
                  <th style={{ textAlign: "left" }}>{t("to")}</th>
                  <th style={{ textAlign: "right" }}>{t("days")}</th>
                  <th />
                </tr></thead>
                <tbody>
                  {temps.map((x, i) => {
                    const dias = Math.round(
                      (new Date(x.hasta).getTime() - new Date(x.desde).getTime())
                      / 86400000) + 1;
                    return (
                      <tr key={i}>
                        <td style={TDL}>
                          <select value={x.temporada} disabled={locked} className="fin-input"
                                  style={{ fontSize: 12.5 }}
                                  onChange={e => setTemps(xs => xs.map((y, j) =>
                                    j === i ? { ...y, temporada: e.target.value } : y))}>
                            {TEMPORADAS.map(s =>
                              <option key={s} value={s}>{t(`season${s}`)}</option>)}
                          </select>
                        </td>
                        {(["desde", "hasta"] as const).map(k => (
                          <td key={k} style={TDL}>
                            <input type="date" value={x[k]} disabled={locked}
                                   className="fin-input" style={{ fontSize: 12.5 }}
                                   onChange={e => setTemps(xs => xs.map((y, j) =>
                                     j === i ? { ...y, [k]: e.target.value } : y))} />
                          </td>))}
                        <td style={TD}>{isNaN(dias) ? "—" : fmtInt(dias)}</td>
                        <td style={TD}>
                          <button disabled={locked} style={{ ...btn(!locked), padding: "3px 9px" }}
                                  onClick={() => setTemps(xs => xs.filter((_, j) => j !== i))}>
                            ✕
                          </button>
                        </td>
                      </tr>);
                  })}
                  <tr>
                    <td colSpan={3} style={{ ...TDL, fontWeight: 700 }}>
                      {t("daysCovered")}
                    </td>
                    <td style={{ ...TD, fontWeight: 700 }}>
                      {fmtInt(data.meses.reduce(
                        (a, m) => a + m.dias - m.dias_sin_temporada, 0))} / {
                        fmtInt(data.meses.reduce((a, m) => a + m.dias, 0))}
                    </td>
                    <td />
                  </tr>
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button disabled={locked} style={btn(!locked)}
                        onClick={() => setTemps(xs => [...xs, {
                          temporada: "VERDE",
                          desde: `${data.year}-01-01`, hasta: `${data.year}-01-31` }])}>
                  + {t("addSeason")}
                </button>
                <button disabled={locked || saving} style={btn(!locked && !saving)}
                        onClick={() => guardar(() => saveRackTemporadas(scenarioId, temps))}>
                  {saving ? tc("saving") : tc("save")}
                </button>
              </div>
            </div>)}

          {/* ── 3 · Resumen Manual: el punto de entrada ─────────────────────
              Es la pestaña `Resumen Manual` del libro, para Proyección 2027.

              ⚠️ **Acá se digitan DOS cosas y nada más**: las noches por
              segmento y mes, y el % de comisión del segmento. Es exactamente
              lo que está escrito a mano en el libro del owner — el resto de
              esa hoja es fórmula (`D9 = D8*D10`, `D10 = D$66*(1-$B$67)`,
              `D11 = D8/D$56`).

              Las tres filas derivadas van PEGADAS a la que se edita, y no en
              otra pantalla: el punto de todo esto es cambiar un número y ver
              el efecto sin ir a buscarlo. */}
          {paso === "noches" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 4 }}>
                {t("inputHint")}
              </p>
              <p style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 10 }}>
                {dirty
                  ? <span style={{ color: "var(--warning, #F59E0B)" }}>● {t("previewing")}</span>
                  : <span>● {t("saved2")}</span>}
              </p>

              {/* ── La plantilla de Excel ───────────────────────────────── */}
              <div style={{ padding: 12, borderRadius: 6, marginBottom: 14,
                            background: "var(--bg-surface)",
                            border: "1px solid var(--border-medium)" }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center",
                              flexWrap: "wrap" }}>
                  <button onClick={bajar} style={excelBtn}>⬇ {t("downloadTemplate")}</button>
                  <input type="file" accept=".xlsx" disabled={locked}
                         onChange={e => { setArchivo(e.target.files?.[0] ?? null);
                                          setCambios(null); setRechazos([]); }}
                         style={{ fontSize: 12.5, color: "var(--text-secondary)" }} />
                  <button disabled={!archivo || subiendo || locked}
                          style={btn(!!archivo && !subiendo && !locked)}
                          onClick={() => subir(false)}>
                    {subiendo ? t("checking") : t("checkFile")}
                  </button>
                  {cambios !== null && cambios.length > 0 && (
                    <button disabled={subiendo} style={btn(!subiendo)}
                            onClick={() => subir(true)}>
                      {t("applyN", { n: cambios.length })}
                    </button>)}
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: 12,
                            marginTop: 8, marginBottom: 0 }}>
                  {t("templateHint")}
                </p>

                {cambios !== null && (
                  <div style={{ marginTop: 10 }}>
                    {cambios.length === 0 && rechazos.length === 0 && (
                      <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                        {t("noChanges")}
                      </div>)}
                    {cambios.length > 0 && (
                      <div style={{ maxHeight: 190, overflowY: "auto" }}>
                        <table className="fin-table" style={{ fontSize: 12 }}>
                          <thead><tr>
                            <th style={{ textAlign: "left" }}>{t("segment")}</th>
                            <th style={{ textAlign: "left" }}>{t("field")}</th>
                            <th style={{ textAlign: "left" }}>{t("month")}</th>
                            <th style={{ textAlign: "right" }}>{t("before")}</th>
                            <th style={{ textAlign: "right" }}>{t("after")}</th>
                          </tr></thead>
                          <tbody>
                            {cambios.map((c, i) => (
                              <tr key={i}>
                                <td style={TDL}>{c.segmento}</td>
                                <td style={TDL}>{c.campo}</td>
                                <td style={TDL}>{c.mes ? MONTHS[c.mes - 1] : "—"}</td>
                                <td style={TD}>{c.antes}</td>
                                <td style={{ ...TD, fontWeight: 700 }}>{c.ahora}</td>
                              </tr>))}
                          </tbody>
                        </table>
                      </div>)}
                    {rechazos.length > 0 && (
                      <div style={{ ...AVISO, marginTop: 8, marginBottom: 0 }}>
                        <b>{t("rejected", { n: rechazos.length })}</b>
                        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                          {rechazos.slice(0, 12).map((x, i) => (
                            <li key={i}>
                              {x.clave}{x.mes ? ` · ${MONTHS[x.mes - 1]}` : ""}
                              {x.campo ? ` · ${x.campo}` : ""} — {x.motivo}
                            </li>))}
                        </ul>
                      </div>)}
                  </div>)}
              </div>

              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1340 }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", minWidth: 250 }}>{t("segment")}</th>
                    <th style={{ textAlign: "right", minWidth: 86 }}>{t("commission")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 82 }}>{m}</th>)}
                    <th style={{ textAlign: "right", minWidth: 96 }}>{tc("total")}</th>
                  </tr></thead>
                  <tbody>
                    {segs.map((s, fi) => {
                      const propia = propias.has(s.code);
                      return (
                        <React.Fragment key={s.code}>
                          {/* El nombre del segmento + su comisión, que es el
                              otro input de esta pestaña (B67:B73 del libro). */}
                          <tr>
                            <td style={{ ...TDL, fontWeight: 700, paddingTop: 12 }}>
                              {s.nombre}
                              {!s.genera_ingreso && (
                                <span title={t("noRevenueHint")}
                                      style={{ marginLeft: 6, fontSize: 11, fontWeight: 400,
                                               color: "var(--text-secondary)" }}>
                                  ({t("noRevenue")})
                                </span>)}
                            </td>
                            <td style={{ ...TD, paddingTop: 12 }}>
                              {s.genera_ingreso && !propia && (
                                <>
                                  <input value={coms[s.code]?.[1] ?? "0"} disabled={locked}
                                         style={{ ...inpNum, width: 62 }}
                                         title={t("commissionHint")}
                                         onChange={e => {
                                           // Enero arrastra a los meses que
                                           // seguían a enero; los cambiados a
                                           // mano se quedan. Misma regla que el
                                           // servidor (`replicar_desde_enero`).
                                           const pct = e.target.value;
                                           setComs(v => {
                                             const antes = v[s.code]?.[1];
                                             const fila = { ...(v[s.code] ?? {}) };
                                             for (let m = 1; m <= 12; m++) {
                                               if (m === 1 || antes === undefined
                                                   || fila[m] === antes) fila[m] = pct;
                                             }
                                             return { ...v, [s.code]: fila };
                                           });
                                           setDirty(true);
                                         }} />
                                  {mesesDistintos(s.code).length > 0 && (
                                    <span title={t("commissionVariesHint")}
                                          style={{ marginLeft: 5, fontSize: 10.5,
                                                   color: "var(--warning, #F59E0B)" }}>
                                      +{mesesDistintos(s.code).length}
                                    </span>)}
                                </>)}
                              {propia && (
                                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                                  {t("ownRate")}
                                </span>)}
                            </td>
                            <td colSpan={13} />
                          </tr>

                          {/* INPUT · las noches */}
                          <tr>
                            <td style={{ ...TDL, paddingLeft: 20 }}>{t("rowNights")}</td>
                            <td />
                            {MONTHS.map((_, mi) => (
                              <td key={mi} style={TD}>
                                <input value={noches[s.code]?.[mi + 1] ?? ""} disabled={locked}
                                       style={{ ...inpNum, width: 66,
                                                borderColor: "var(--brand)" }}
                                       onPaste={e => manejarPegado(e, b => pegarNoches(fi, mi, b))}
                                       onChange={e => {
                                         setNoches(v => ({ ...v,
                                           [s.code]: { ...(v[s.code] ?? {}),
                                                       [mi + 1]: e.target.value } }));
                                         setDirty(true);
                                       }} />
                              </td>))}
                            <td style={{ ...TD, fontWeight: 600 }}>
                              {fmtInt(MONTHS.reduce(
                                (a, _, mi) => a + n(noches[s.code]?.[mi + 1]), 0))}
                            </td>
                          </tr>

                          {/* INPUT sólo para los de tarifa propia: Long term
                              no tiene RAC, así que su tarifa se digita. */}
                          {propia && (
                            <tr>
                              <td style={{ ...TDL, paddingLeft: 20 }}>{t("rowOwnRate")}</td>
                              <td />
                              {MONTHS.map((_, mi) => (
                                <td key={mi} style={TD}>
                                  <input value={tarifasPropias[s.code]?.[mi + 1] ?? ""}
                                         disabled={locked}
                                         style={{ ...inpNum, width: 66,
                                                  borderColor: "var(--brand)" }}
                                         onPaste={e => manejarPegado(e, b => pegarTarifas(
                                           conTarifaPropia.findIndex(x => x.code === s.code), mi, b))}
                                         onChange={e => {
                                           setTarifasPropias(v => ({ ...v,
                                             [s.code]: { ...(v[s.code] ?? {}),
                                                         [mi + 1]: e.target.value } }));
                                           setDirty(true);
                                         }} />
                                </td>))}
                              <td />
                            </tr>)}

                          {/* DERIVADAS · las tres filas de fórmula del libro */}
                          <Der l={t("rowRevenue")}
                               v={m => n(m.segmentos[s.code]?.ingreso)} f={fmtUsd}
                               t={n(vista?.total?.segmentos[s.code]?.ingreso)} />
                          {s.genera_ingreso && (
                            <Der l={t("rowAvgRate")}
                                 v={m => n(m.segmentos[s.code]?.tarifa)} f={fmtUsd} />)}
                          <Der l={t("rowOccupancy")}
                               v={m => n(m.segmentos[s.code]?.ocupacion)} f={fmtPct} />
                        </React.Fragment>);
                    })}

                    {/* ── TOTALES ─────────────────────────────────────────── */}
                    <tr><td style={BLQ} colSpan={15}>{t("blockTotals")}</td></tr>
                    <Tot l={t("available")} v={m => n(m.disponibles)}
                         t={n(vista?.total.disponibles)} f={fmtInt} />
                    <Tot l={t("nightsRevenue")} v={m => n(m.noches_ingreso)}
                         t={n(vista?.total.noches_ingreso)} f={fmtInt} />
                    <Tot l={t("nightsTotal")} v={m => n(m.noches_totales)}
                         t={n(vista?.total.noches_totales)} f={fmtInt} />
                    <Tot l={t("occupancy")} v={m => n(m.ocupacion)}
                         t={n(vista?.total.ocupacion)} f={fmtPct} />
                    <Tot l={t("occupancyTotal")} v={m => n(m.ocupacion_total)}
                         t={n(vista?.total.ocupacion_total)} f={fmtPct} />
                    <Tot l={t("totalNetRevenue")} bold v={m => n(m.ingreso)}
                         t={n(vista?.total.ingreso)} f={fmtUsd} />
                    <Tot l={t("adr")} v={m => n(m.adr)} t={n(vista?.total.adr)} f={fmtUsd} />
                    <Tot l={t("revpar")} v={m => n(m.revpar)}
                         t={n(vista?.total.revpar)} f={fmtUsd} />

                    {/* ── El RAC del que sale todo ────────────────────────── */}
                    <tr><td style={BLQ} colSpan={15}>{t("blockRackRate")}</td></tr>
                    <Tot l={t("racWeighted")} v={m => n(m.rac_ponderado)}
                         t={n(vista?.total?.rack.adr_rack_sin_propias)} f={fmtUsd}
                         hint={t("racWeightedHint")} />
                  </tbody>
                </table>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
                <button disabled={locked || saving || !dirty}
                        style={btn(!locked && !saving && dirty)}
                        onClick={guardarEntrada}>
                  {saving ? tc("saving") : tc("save")}
                </button>
                {dirty && (
                  <button disabled={saving} style={{ ...btn(!saving),
                            background: "var(--bg-surface)", color: "var(--text-secondary)" }}
                          onClick={() => { if (data) aplicar2(data); }}>
                    {t("discard")}
                  </button>)}
              </div>
            </div>)}

          {/* ── 4 · Origen de la tarifa ────────────────────────────────────── */}
          {paso === "origen" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("originHint")}
              </p>

              {/* Las comisiones: el único input de esta pantalla */}
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                {t("commissionsTitle")}
              </h3>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5,
                          marginBottom: 8 }}>
                {t("commissionMonthlyHint")}
              </p>
              <div className="fin-sticky" style={{ overflowX: "auto", marginBottom: 14 }}>
                <table className="fin-table" style={{ minWidth: 1200 }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", minWidth: 220 }}>{t("segment")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 74 }}>{m}</th>)}
                    <th style={{ textAlign: "left", minWidth: 110 }}>{t("ownRate")}</th>
                  </tr></thead>
                  <tbody>
                    {segs.filter(x => x.genera_ingreso).map(x => {
                      const propia = propias.has(x.code);
                      const ene = n(coms[x.code]?.[1]);
                      return (
                        <tr key={x.code}>
                          <td style={TDL}>{x.nombre}</td>
                          {MONTHS.map((_, mi) => {
                            const mes = mi + 1;
                            const difiere = mes > 1 && n(coms[x.code]?.[mes]) !== ene;
                            return (
                              <td key={mi} style={TD}>
                                {propia ? <span style={{ fontSize: 11,
                                                         color: "var(--text-secondary)" }}>—</span>
                                 : <input value={coms[x.code]?.[mes] ?? "0"}
                                          disabled={locked}
                                          style={{ ...inpNum, width: 60,
                                                   // El mes que se apartó de
                                                   // enero se marca: si no, un
                                                   // ajuste puntual queda
                                                   // invisible entre doce
                                                   // celdas iguales.
                                                   borderColor: difiere
                                                     ? "var(--warning, #F59E0B)"
                                                     : "var(--border-medium)" }}
                                          onChange={e => {
                                            setComs(v => ({ ...v,
                                              [x.code]: { ...(v[x.code] ?? {}),
                                                          [mes]: e.target.value } }));
                                            setDirty(true);
                                          }} />}
                              </td>);
                          })}
                          <td style={TDL}>
                            <input type="checkbox" checked={propia} disabled={locked}
                                   onChange={e => {
                                     setPropiaDe(v => ({ ...v, [x.code]: e.target.checked }));
                                     setDirty(true);
                                   }} />
                          </td>
                        </tr>);
                    })}
                  </tbody>
                </table>
              </div>
              <button disabled={locked || saving} style={{ ...btn(!locked && !saving), marginBottom: 20 }}
                      onClick={() => guardar(() => saveRackComisiones(scenarioId, comisionesAEnviar()))}>
                {saving ? tc("saving") : tc("save")}
              </button>

              {/* El camino, mes a mes: días → RAC por villa → RAC ponderado */}
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                {t("pathTitle")}
              </h3>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1180 }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", minWidth: 210 }}>{t("concept")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                  </tr></thead>
                  <tbody>
                    {TEMPORADAS.map(s => (
                      <tr key={s}>
                        <td style={TDL}>{t("daysIn")} {t(`season${s}`)}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtInt(m.dias_por_temporada[s] ?? 0)}
                          </td>))}
                      </tr>))}
                    <tr>
                      <td style={{ ...TDL, color: "var(--negative)" }}>
                        {t("daysNoSeason")}
                      </td>
                      {data.meses.map(m => (
                        <td key={m.month} style={{ ...TD,
                          color: m.dias_sin_temporada ? "var(--negative)" : undefined,
                          fontWeight: m.dias_sin_temporada ? 700 : undefined }}>
                          {fmtInt(m.dias_sin_temporada)}
                        </td>))}
                    </tr>
                    {villas.map(v => (
                      <tr key={v.villa}>
                        <td style={TDL}>RAC · {v.villa}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtUsd(n(m.rac_por_villa[v.villa]))}
                          </td>))}
                      </tr>))}
                    <tr>
                      <td style={{ ...TDL, fontWeight: 700 }}>{t("racWeighted")}</td>
                      {data.meses.map(m => (
                        <td key={m.month} style={{ ...TD, fontWeight: 700 }}>
                          {fmtUsd(n(m.rac_ponderado))}
                        </td>))}
                    </tr>
                    {segs.filter(s => s.genera_ingreso).map(s => (
                      <tr key={s.code}>
                        <td style={TDL}>{t("netRateOf")} {s.nombre}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtUsd(n(m.segmentos[s.code]?.tarifa))}
                          </td>))}
                      </tr>))}
                  </tbody>
                </table>
              </div>
            </div>)}

          {/* ── 5 · KPIs Rack ──────────────────────────────────────────────── */}
          {/* ── 5 · KPIs Rack ──────────────────────────────────────────────
              Es la pestaña `KPIs Rack` del libro del owner, bloque por bloque.

              ⚠️ **Los dos lados van juntos.** El NETO es lo que entra al P&L;
              el RACK es contra lo que se mide el descuento del canal. Mostrar
              sólo el neto deja «vendimos a $177,68» sin nada con qué
              compararse, y la comisión sin denominador. */}
          {paso === "kpis" && (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ minWidth: 1340 }}>
                <thead><tr>
                  <th style={{ textAlign: "left", minWidth: 250 }}>{t("concept")}</th>
                  {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 84 }}>{m}</th>)}
                  <th style={{ textAlign: "right", minWidth: 100 }}>{tc("total")}</th>
                </tr></thead>
                <tbody>
                  {/* ── Capacidad y ocupación ───────────────────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockCapacity")}</td></tr>
                  <Fila l={t("available")} v={m => n(m.disponibles)}
                        t={n(data.total.disponibles)} f={fmtInt} />
                  <Fila l={t("nightsRevenue")} v={m => n(m.rack.noches_facturadas)}
                        t={n(data.total.rack.noches_facturadas)} f={fmtInt} />
                  <Fila l={t("nightsOwnRate")} sub v={m => n(m.rack.noches_tarifa_propia)}
                        t={n(data.total.rack.noches_tarifa_propia)} f={fmtInt} />
                  <Fila l={t("nightsComp")} v={m => n(m.rack.noches_cortesia)}
                        t={n(data.total.rack.noches_cortesia)} f={fmtInt} />
                  <Fila l={t("occupancy")} v={m => n(m.ocupacion)}
                        t={n(data.total.ocupacion)} f={fmtPct} />
                  <Fila l={t("occupancyTotal")} v={m => n(m.ocupacion_total)}
                        t={n(data.total.ocupacion_total)} f={fmtPct}
                        hint={t("occupancyTotalHint")} />

                  {/* ── Tarifa rack ─────────────────────────────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockRackRate")}</td></tr>
                  <Fila l={t("racWeighted")} v={m => n(m.rac_ponderado)}
                        t={n(data.total.rack.adr_rack_sin_propias)} f={fmtUsd} />

                  {/* ── Ingreso a precio rack, por segmento ─────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockRackRevenue")}</td></tr>
                  {segs.filter(s => s.genera_ingreso).map(s => (
                    <tr key={s.code}>
                      <td style={TDL}>
                        {s.nombre}
                        {propias.has(s.code) && (
                          <span style={{ marginLeft: 6, fontSize: 11,
                                         color: "var(--text-secondary)" }}>
                            ({t("ownRate")})
                          </span>)}
                      </td>
                      {data.meses.map(m => (
                        <td key={m.month} style={TD}>
                          {fmtUsd(n(m.segmentos[s.code]?.ingreso_rack))}
                        </td>))}
                      <td style={{ ...TD, fontWeight: 700 }}>
                        {fmtUsd(data.meses.reduce(
                          (a, m) => a + n(m.segmentos[s.code]?.ingreso_rack), 0))}
                      </td>
                    </tr>))}
                  <Fila l={t("totalRackRevenue")} bold v={m => n(m.rack.ingreso_rack)}
                        t={n(data.total.rack.ingreso_rack)} f={fmtUsd} />

                  {/* ── KPIs a precio rack ──────────────────────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockRackKpis")}</td></tr>
                  <Fila l={t("adrRack")} v={m => n(m.rack.adr_rack)}
                        t={n(data.total.rack.adr_rack)} f={fmtUsd} />
                  <Fila l={t("adrRackNoOwn")} v={m => n(m.rack.adr_rack_sin_propias)}
                        t={n(data.total.rack.adr_rack_sin_propias)} f={fmtUsd}
                        hint={t("adrRackNoOwnHint")} />
                  <Fila l={t("revparRack")} v={m => n(m.rack.revpar_rack)}
                        t={n(data.total.rack.revpar_rack)} f={fmtUsd} />

                  {/* ── Rack contra neto ────────────────────────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockRackVsNet")}</td></tr>
                  <Fila l={t("totalNetRevenue")} bold v={m => n(m.rack.ingreso_neto)}
                        t={n(data.total.rack.ingreso_neto)} f={fmtUsd}
                        hint={t("totalNetRevenueHint")} />
                  <Fila l={t("adrNet")} v={m => n(m.rack.adr_neto)}
                        t={n(data.total.rack.adr_neto)} f={fmtUsd} />
                  <Fila l={t("revparNet")} v={m => n(m.rack.revpar_neto)}
                        t={n(data.total.rack.revpar_neto)} f={fmtUsd} />
                  <Fila l={t("commissionUsd")} v={m => n(m.rack.comision_usd)}
                        t={n(data.total.rack.comision_usd)} f={fmtUsd} />
                  <Fila l={t("commissionPct")} v={m => n(m.rack.comision_pct)}
                        t={n(data.total.rack.comision_pct)} f={fmtPct} />
                  <Fila l={t("rackKept")} v={m => n(m.rack.pct_rack_retenido)}
                        t={n(data.total.rack.pct_rack_retenido)} f={fmtPct}
                        hint={t("rackKeptHint")} />

                  {/* ── Mix de ingreso rack ─────────────────────────────── */}
                  <tr><td style={BLQ} colSpan={14}>{t("blockRackMix")}</td></tr>
                  {segs.filter(s => s.genera_ingreso).map(s => (
                    <tr key={s.code}>
                      <td style={TDL}>{s.nombre}</td>
                      {data.meses.map(m => (
                        <td key={m.month} style={TD}>
                          {fmtPct(n(m.mix_rack?.[s.code]))}
                        </td>))}
                      <td style={{ ...TD, fontWeight: 700 }}>
                        {fmtPct(n(data.total.mix_rack?.[s.code]))}
                      </td>
                    </tr>))}
                </tbody>
              </table>
            </div>)}

          {/* ── 6 · Conexión ───────────────────────────────────────────────── */}
          {paso === "conexion" && (
            <div style={{ maxWidth: 760 }}>
              <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 14 }}>
                {t("connectHint")}
              </p>
              <div style={{ padding: 16, borderRadius: 6, background: "var(--bg-surface)",
                            border: "1px solid var(--border-medium)" }}>
                <div style={{ fontSize: 13, marginBottom: 12 }}>
                  {t("currentModel")}: <b>{data.conectado ? t("modelChannels") : t("modelRates")}</b>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button disabled={locked || saving || data.conectado}
                          style={btn(!locked && !saving && !data.conectado)}
                          onClick={() => guardar(async () => {
                            await conectarRackRooms(scenarioId, "canales");
                            return getRackRooms(scenarioId);
                          })}>
                    {t("connect")}
                  </button>
                  <button disabled={locked || saving || !data.conectado}
                          style={btn(!locked && !saving && data.conectado)}
                          onClick={() => guardar(async () => {
                            await conectarRackRooms(scenarioId, "tarifas");
                            return getRackRooms(scenarioId);
                          })}>
                    {t("disconnect")}
                  </button>
                  <button disabled={recalc} style={btn(!recalc)} onClick={recalcular}>
                    {recalc ? t("recalculating") : t("recalculate")}
                  </button>
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginTop: 12 }}>
                  {t("connectWarning")}
                </p>
              </div>
            </div>)}
        </>
      )}
    </div>
  );
}
