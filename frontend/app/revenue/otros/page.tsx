"use client";
/**
 * Ingresos → Otros. Las líneas que se digitan, un monto por mes.
 *
 * Owner, 2026-10-08: *«todas las líneas de ingreso deben estar acá; si meto
 * otras que no están deben aparecer acá»*.
 *
 * **Por qué existe.** En modo `drivers` el checkbook es un ESPEJO: cada
 * recálculo lo reescribe desde el modelo, así que digitar ahí no sirve — se
 * borra en silencio y el P&L sigue cuadrando contra el número equivocado. La
 * fuente de verdad de estas líneas es `revenue_other`, y hasta hoy sólo la
 * escribían el Spa y el Club, que tienen pantalla propia. Tours, Transporte,
 * Retail, Lavandería y Misceláneos no tenían dónde presupuestarse: $256.878
 * reales en Oxygen contra cero, sin ningún aviso.
 *
 * **La lista no está escrita acá.** Viene del backend, derivada de
 * `OTHER_REVENUE_LINES`. Una línea de ingreso nueva aparece sola — que es
 * literalmente lo que pidió el owner.
 *
 * **Las líneas con driver se ven y no se tocan.** Su monto lo calcula otra
 * pantalla; dejarlas editables acá daría dos verdades y mandaría la última en
 * guardar. Se muestran igual porque esconderlas haría que el cuadro no sume el
 * ingreso del escenario.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { usePlanningScenarioConUrl } from "@/lib/planningScenario";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { manejarPegado, repartirPegado, numeroDeExcel } from "@/lib/pegarGrilla";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getIngresosPlanos, saveIngresosPlanos,
  type Scenario, type IngresosPlanosResponse,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";
import InputMoneda from "@/components/InputMoneda";
import Monto from "@/components/Monto";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const n = (v: string | number | undefined) => {
  const x = parseFloat(String(v ?? "").replace(/[, %$]/g, ""));
  return isNaN(x) ? 0 : x;
};
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

const btn = (on: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: on ? "pointer" : "not-allowed", border: "none",
  background: on ? "var(--brand)" : "var(--bg-surface)",
  color: on ? "#fff" : "var(--text-disabled)",
});
const inp: React.CSSProperties = {
  width: 88, textAlign: "right", padding: "4px 6px", fontSize: 13,
  borderRadius: 4, border: "1px solid var(--border-medium)",
  background: "var(--bg-base)", color: "var(--text-primary)",
  fontVariantNumeric: "tabular-nums",
};
const TD: React.CSSProperties = { padding: "5px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" };
const TH: React.CSSProperties = { ...TD, fontWeight: 600, color: "var(--text-secondary)", fontSize: 12 };

export default function OtrosIngresosPage() {
  const tc = useTranslations("common");
  const t = useTranslations("otrosIngresos");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [data, setData] = useState<IngresosPlanosResponse | null>(null);
  /** line → 12 montos, como texto, para que se pueda escribir sin pelear. */
  const [vals, setVals] = useState<Record<string, string[]>>({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      const d = await getIngresosPlanos(sid);
      setData(d);
      setVals(Object.fromEntries(d.lineas.map(l => [l.line, l.meses.map(m => String(n(m)))])));
      setDirty(false);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [tc]);

  useEffect(() => { if (scenarioId) cargar(scenarioId); }, [scenarioId, cargar]);

  const bloqueado = !!data?.locked;
  const lineas = data?.lineas ?? [];
  const totalLinea = (ln: string) => (vals[ln] ?? []).reduce((a, v) => a + n(v), 0);
  const totalMes = (i: number) => lineas.reduce((a, l) => a + n((vals[l.line] ?? [])[i]), 0);
  const granTotal = lineas.reduce((a, l) => a + totalLinea(l.line), 0);

  function set(ln: string, i: number, v: string) {
    setVals(p => {
      const fila = [...(p[ln] ?? Array(12).fill("0"))];
      fila[i] = v;
      return { ...p, [ln]: fila };
    });
    setDirty(true);
  }

  /**
   * Pegar desde Excel: un bloque de filas x meses entra donde se soltó.
   *
   * ⚠️ Las filas con driver se SALTAN y el bloque sigue bajando. Escribirles
   * encima no serviría —el backend las rechaza— y detenerse ahí partiría el
   * pegado a la mitad sin decir por qué.
   */
  function pegar(fila: number, mes: number, bloque: string[][]) {
    const editables = lineas;
    setVals(p => {
      const out = { ...p };
      repartirPegado(bloque, fila, mes, editables.length, 12, (f, c, valor) => {
        const l = editables[f];
        if (!l || l.driver) return;
        const actual = [...(out[l.line] ?? Array(12).fill("0"))];
        actual[c] = String(numeroDeExcel(valor));
        out[l.line] = actual;
      });
      return out;
    });
    setDirty(true);
  }

  /** Repite enero en los doce meses. Un gasto parejo no se teclea doce veces. */
  function parejo(ln: string) {
    const v = (vals[ln] ?? [])[0] ?? "0";
    setVals(p => ({ ...p, [ln]: Array(12).fill(v) }));
    setDirty(true);
  }

  async function guardar() {
    if (!scenarioId) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      // Las de driver no se mandan: el backend las rechaza con 409 y tiene
      // razón, pero mandarlas sería pedir el error a propósito.
      const cuerpo = lineas.filter(l => !l.driver).map(l => ({
        line: l.line, meses: (vals[l.line] ?? Array(12).fill("0")).map(n),
      }));
      const d = await saveIngresosPlanos(scenarioId, cuerpo);
      setData(d);
      setVals(Object.fromEntries(d.lineas.map(l => [l.line, l.meses.map(m => String(n(m)))])));
      setDirty(false); setMsg(t("saved"));
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

  async function bajarExcel() {
    const sel = scenarios.find(x => x.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const cuerpo: FilaCuadro[] = lineas.map(l => ({
      label: l.label,
      valores: [...(vals[l.line] ?? Array(12).fill("0")).map(n), totalLinea(l.line)],
    }));
    cuerpo.push({
      label: tc("total"), es_total: true,
      suma_de: lineas.map((_l, i) => i),
      valores: [...MONTHS.map((_m, i) => totalMes(i)), granTotal],
    });
    try {
      await bajarCuadros("Otros_Ingresos", [{
        titulo: t("title"), subtitulo: esc, hoja: t("sheet"),
        columnas: [
          { label: t("line"), ancho: 28, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 13, formato: "usd2" as const })),
          { label: tc("total"), ancho: 15, formato: "usd2" as const },
        ],
        filas: cuerpo,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 24px" }}>
      <IrA esc={scenarioId} />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("title")}</h1>
      <p style={{ maxWidth: "88ch", fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
        {t("intro")}
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
        <select className="fin-input" value={scenarioId}
          onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "6px 10px", fontSize: 13, minWidth: 230, fontWeight: 600 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={guardar} disabled={!dirty || saving || bloqueado} style={btn(dirty && !saving && !bloqueado)}>
          {saving ? tc("saving") : tc("save")}
        </button>
        <button onClick={recalcular} disabled={recalc || bloqueado} style={btn(!recalc && !bloqueado)}>
          {recalc ? tc("recalc.running") : t("recalc")}
        </button>
        <button onClick={bajarExcel} disabled={loading}
          style={{ padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 6,
                   cursor: loading ? "default" : "pointer", background: "transparent",
                   color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {msg && <div style={{ color: "var(--positive, #26A69A)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? <div style={{ padding: 24 }}>{tc("loading")}</div> : (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...TH, textAlign: "left", minWidth: 210 }}>{t("line")}</th>
                {MONTHS.map(m => <th key={m} style={TH}>{m}</th>)}
                <th style={TH}>{tc("total")}</th>
              </tr>
            </thead>
            <tbody>
              {lineas.map(l => (
                <tr key={l.line} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...TD, textAlign: "left", fontWeight: 600 }}>
                    {l.label}
                    {l.driver ? (
                      <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 400, color: "var(--text-disabled)" }}
                        title={t("driverHint")}>· {t("driverTag")}</span>
                    ) : (
                      <button onClick={() => parejo(l.line)} disabled={bloqueado}
                        title={t("evenHint")}
                        style={{ marginLeft: 6, fontSize: 11, padding: "1px 6px", borderRadius: 4,
                                 border: "1px solid var(--border-medium)", background: "transparent",
                                 color: "var(--text-secondary)",
                                 cursor: bloqueado ? "default" : "pointer" }}>
                        {t("even")}
                      </button>
                    )}
                  </td>
                  {MONTHS.map((_m, i) => (
                    <td key={i} style={TD}>
                      {l.driver ? (
                        <span style={{ color: "var(--text-secondary)" }}>
                          {usd(n((vals[l.line] ?? [])[i]))}
                        </span>
                      ) : (
                        <InputMoneda
                          value={(vals[l.line] ?? [])[i] ?? "0"} disabled={bloqueado}
                          onChange={v => set(l.line, i, v)}
                          onPaste={e => manejarPegado(e, b => pegar(lineas.indexOf(l), i, b))}
                          style={inp} />
                      )}
                    </td>
                  ))}
                  <td style={{ ...TD, fontWeight: 700 }}><Monto>{usd(totalLinea(l.line))}</Monto></td>
                </tr>
              ))}
              <tr style={{ borderTop: "2px solid var(--border-medium)", fontWeight: 700 }}>
                <td style={{ ...TD, textAlign: "left" }}>{tc("total")}</td>
                {MONTHS.map((_m, i) => <td key={i} style={TD}><Monto>{usd(totalMes(i))}</Monto></td>)}
                <td style={TD}><Monto>{usd(granTotal)}</Monto></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
