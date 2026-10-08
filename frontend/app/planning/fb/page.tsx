"use client";
/**
 * Planning → A&B. Del pax a la comida, y de la comida al ingreso.
 *
 * Owner, 2026-10-03: *«food and beverage es un departamento importante…
 * necesito crear un sub tab en planning para calcular estos ingresos… partir de
 * las estadísticas de rooms, rooms occupied y total pax por mes. y también hay
 * una cantidad de pax externos»*.
 *
 * **Los pax hospedados NO se digitan acá.** Salen de las estadísticas del
 * escenario, que es lo que la pantalla de Rooms ya calculó. Dos lugares para
 * escribir el mismo mes es dos verdades y ninguna manda.
 *
 * **La captura es la razón de ser de la pantalla.** Multiplicar pax por las tres
 * comidas da el techo, no el ingreso: medido contra el mayor de Oxygen, 6.643
 * pax-noche × $126 daría $837.018 contra $228.608 reales. Por eso cada comida
 * lleva su propio porcentaje y no uno solo: el desayuno del huésped se consume
 * casi siempre y la cena bastante menos.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { usePlanningScenarioConUrl } from "@/lib/planningScenario";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getFbPlan, saveFbPlan, fbPlanAlCheckbook,
  type Scenario, type FbPlanResponse,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const COMIDAS = ["desayuno", "almuerzo", "cena"] as const;
type Comida = typeof COMIDAS[number];

const n = (v: string | number | undefined) => {
  const x = parseFloat(String(v ?? "").replace(/[, %$]/g, ""));
  return isNaN(x) ? 0 : x;
};
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ent = (v: number) => Math.round(v).toLocaleString("en-US");

const btn = (on: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: on ? "pointer" : "not-allowed", border: "none",
  background: on ? "var(--brand)" : "var(--bg-surface)",
  color: on ? "#fff" : "var(--text-disabled)",
});
const inp: React.CSSProperties = {
  width: 92, textAlign: "right", padding: "4px 6px", fontSize: 13,
  borderRadius: 4, border: "1px solid var(--border-medium)",
  background: "var(--bg-base)", color: "var(--text-primary)",
  fontVariantNumeric: "tabular-nums",
};
const TD: React.CSSProperties = { padding: "5px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" };
const TH: React.CSSProperties = { ...TD, fontWeight: 600, color: "var(--text-secondary)", fontSize: 12 };

export default function FbPlanPage() {
  const tc = useTranslations("common");
  const t = useTranslations("fbPlan");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [data, setData] = useState<FbPlanResponse | null>(null);

  // Precios en USD; capturas y porcentajes en NÚMERO DE PANTALLA (35 = 35%).
  // La conversión a fracción se hace al guardar, en un solo lugar.
  const [precio, setPrecio] = useState<Record<Comida, string>>({ desayuno: "0", almuerzo: "0", cena: "0" });
  const [captura, setCaptura] = useState<Record<Comida, string>>({ desayuno: "0", almuerzo: "0", cena: "0" });
  const [servicio, setServicio] = useState("10");
  const [comisionable, setComisionable] = useState("0");
  const [bevPct, setBevPct] = useState("0");
  const [paxExt, setPaxExt] = useState<string[]>(Array(12).fill("0"));
  const [ticket, setTicket] = useState<string[]>(Array(12).fill("0"));

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
      const d = await getFbPlan(sid);
      setData(d);
      if (d.config) {
        setPrecio({
          desayuno: String(n(d.config.precio_desayuno)),
          almuerzo: String(n(d.config.precio_almuerzo)),
          cena: String(n(d.config.precio_cena)),
        });
        setCaptura({
          desayuno: String(n(d.config.captura_desayuno) * 100),
          almuerzo: String(n(d.config.captura_almuerzo) * 100),
          cena: String(n(d.config.captura_cena) * 100),
        });
        setServicio(String(n(d.config.servicio_pct) * 100));
        setComisionable(String(n(d.config.pct_comisionable) * 100));
        setBevPct(String(n(d.config.bev_pct_food) * 100));
      }
      setPaxExt(d.meses.map(m => String(n(m.pax_externos))));
      setTicket(d.meses.map(m => String(n(m.food_externos) / (n(m.pax_externos) || 1))));
      setDirty(false);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [tc]);

  useEffect(() => { if (scenarioId) cargar(scenarioId); }, [scenarioId, cargar]);

  // Mismo cálculo que el backend (`app/models/fb_plan.py::calcular_mes`), para
  // que el número se mueva mientras se escribe. El que manda es el del
  // servidor: al guardar se vuelve a pintar con lo que él devuelve.
  const filas = (data?.meses ?? []).map((m, i) => {
    const pax = n(m.pax_hospedados);
    const porComida = Object.fromEntries(
      COMIDAS.map(c => [c, pax * n(precio[c]) * (n(captura[c]) / 100)]),
    ) as Record<Comida, number>;
    // 1 · bruto: precio de carta por la fracción que de verdad se consume
    const bruto = COMIDAS.reduce((a, c) => a + porComida[c], 0);
    // 2 · descuento: sólo sobre la parte que viaja con agencia, con el MISMO
    //     factor de canal que netea la tarifa de habitación
    const factor = m.net_factor ? n(m.net_factor) : 1;
    const desc = bruto * (n(comisionable) / 100) * (1 - factor);
    const foodHosp = bruto - desc;
    // 3 · el externo paga en la puerta: sin comisión
    const foodExt = n(paxExt[i]) * n(ticket[i]);
    const food = foodHosp + foodExt;
    // 4 · el servicio se cobra sobre la carta y NO suma al ingreso
    const sc = (bruto + foodExt) * (n(servicio) / 100);
    const bev = food * (n(bevPct) / 100);
    return { mes: i, pax, ...porComida, bruto, desc, foodHosp, foodExt, sc,
             food, bev, total: food + bev };
  });
  const tot = filas.reduce((a, f) => ({
    pax: a.pax + f.pax, bruto: a.bruto + f.bruto, desc: a.desc + f.desc,
    foodHosp: a.foodHosp + f.foodHosp, foodExt: a.foodExt + f.foodExt,
    sc: a.sc + f.sc, food: a.food + f.food, bev: a.bev + f.bev, total: a.total + f.total,
  }), { pax: 0, bruto: 0, desc: 0, foodHosp: 0, foodExt: 0, sc: 0, food: 0, bev: 0, total: 0 });

  const bloqueado = !!data?.locked;

  /**
   * El MISMO cuadro que se ve, a Excel.
   *
   * Lo pedía `test_toda_pantalla_con_cuadro_se_puede_bajar`: toda pantalla que
   * muestra una tabla tiene que dejar bajarla. Esta era la única de la
   * propiedad que no — se miraba y se volvía a teclear en otro lado.
   *
   * ⚠️ Los meses van en FILAS, que es como está la pantalla. Transponerlo para
   * que se parezca a los otros cuadros daría un Excel que no es el que se vio.
   */
  async function bajarExcel() {
    const sel = scenarios.find(x => x.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const fila = (i: number): FilaCuadro => {
      const f = filas[i];
      return { label: MONTHS[i], valores: [
        f.pax, n(paxExt[i]), n(ticket[i]), f.pax + n(paxExt[i]),
        ...COMIDAS.map(c => f[c] as number),
        f.bruto, -f.desc, f.foodExt, f.food, f.bev, f.total, f.sc] };
    };
    const cuerpo = filas.map((_f, i) => fila(i));
    const extTot = paxExt.reduce((a, v) => a + n(v), 0);
    cuerpo.push({ label: tc("total"), es_total: true,
      suma_de: filas.map((_f, i) => i),
      valores: [tot.pax, extTot, 0, tot.pax + extTot,
                ...COMIDAS.map(c => filas.reduce((a, f) => a + (f[c] as number), 0)),
                tot.bruto, -tot.desc, tot.foodExt, tot.food, tot.bev, tot.total,
                tot.sc] });
    try {
      await bajarCuadros("AyB", [{
        titulo: t("title"),
        subtitulo: esc,
        hoja: "A&B",
        columnas: [
          { label: t("month"), ancho: 14, formato: "texto" },
          { label: t("paxInHouse"), ancho: 13, formato: "num" },
          { label: t("paxExternal"), ancho: 13, formato: "num" },
          { label: t("ticket"), ancho: 13, formato: "usd2" },
          { label: t("paxTotal"), ancho: 13, formato: "num" },
          ...COMIDAS.map(c => ({ label: t(`meal_${c}`), ancho: 14, formato: "usd2" as const })),
          { label: t("gross"), ancho: 14, formato: "usd2" },
          { label: t("discount"), ancho: 14, formato: "usd2" },
          { label: t("foodExternal"), ancho: 14, formato: "usd2" },
          { label: t("food"), ancho: 14, formato: "usd2" },
          { label: t("beverage"), ancho: 14, formato: "usd2" },
          { label: t("total"), ancho: 15, formato: "usd2" },
          { label: t("service"), ancho: 15, formato: "usd2" },
        ],
        filas: cuerpo,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }

  async function guardar() {
    if (!scenarioId) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      const d = await saveFbPlan(scenarioId, {
        precio_desayuno: n(precio.desayuno), precio_almuerzo: n(precio.almuerzo),
        precio_cena: n(precio.cena),
        captura_desayuno: n(captura.desayuno) / 100,
        captura_almuerzo: n(captura.almuerzo) / 100,
        captura_cena: n(captura.cena) / 100,
        servicio_pct: n(servicio) / 100,
        pct_comisionable: n(comisionable) / 100,
        bev_pct_food: n(bevPct) / 100,
      }, filas.map((f, i) => ({
        month: i + 1, pax_externos: Math.round(n(paxExt[i])), ticket_externos: n(ticket[i]),
      })));
      setData(d); setDirty(false); setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function alCheckbook() {
    if (!scenarioId) return;
    setSaving(true); setError(null); setMsg(null);
    try {
      const r = await fbPlanAlCheckbook(scenarioId);
      setMsg(t("movedToCheckbook", {
        food: usd(n(r.escritas.FOOD)), bev: usd(n(r.escritas.BEVERAGE)),
      }));
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

  const campo = (label: string, valor: string, set: (v: string) => void, sufijo?: string) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
      {label}
      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <input className="fin-input mono" type="number" value={valor} disabled={bloqueado}
          onChange={e => { set(e.target.value); setDirty(true); }} style={inp} />
        {sufijo && <span style={{ fontSize: 12, color: "var(--text-disabled)" }}>{sufijo}</span>}
      </span>
    </label>
  );

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 24px" }}>
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("title")}</h1>
      <p style={{ maxWidth: "88ch", fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
        {t("intro")}
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
        {/* ⚠️ Ancho mínimo explícito. Sin él el selector se encoge hasta
            mostrar «BUDG…» y no se sabe en cuál escenario se está: el 2026 de
            esta propiedad abre en JUNIO y el 2027 tiene pax los doce meses, así
            que los cinco ceros de arriba se leen como un defecto del cálculo
            cuando son el presupuesto correcto del año equivocado. Pasó el
            2026-10-03, a los diez minutos de publicar la pantalla. */}
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
        {/* `!data?.config` incluido: sin fila guardada el backend contesta 422 y
            bien, pero el botón estaba encendido y lo invitaba a apretarlo. El
            freno se pone antes, no después. */}
        <button onClick={alCheckbook} disabled={saving || bloqueado || dirty || !data?.config}
          title={t("moveHint")} style={btn(!saving && !bloqueado && !dirty && !!data?.config)}>
          {t("moveToCheckbook")}
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

      {data?.sin_estadisticas && (
        <div style={{ padding: "10px 12px", marginBottom: 12, borderRadius: 6,
          background: "var(--bg-surface)", border: "1px solid var(--warning, #F59E0B)", fontSize: 13 }}>
          ⚠️ {t("noStats")}
        </div>
      )}
      {msg && <div style={{ color: "var(--positive, #26A69A)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {/* Precios y captura — por escenario, no por mes */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", padding: "12px 14px", marginBottom: 16,
        borderRadius: 8, border: "1px solid var(--border-medium)", background: "var(--bg-surface)" }}>
        {COMIDAS.map(c => campo(t(`price_${c}`), precio[c], v => setPrecio(p => ({ ...p, [c]: v })), "$"))}
        {COMIDAS.map(c => campo(t(`capture_${c}`), captura[c], v => setCaptura(p => ({ ...p, [c]: v })), "%"))}
        {campo(t("commissionable"), comisionable, setComisionable, "%")}
        {campo(t("bevPctFood"), bevPct, setBevPct, "%")}
        {campo(t("serviceCharge"), servicio, setServicio, "%")}
      </div>

      {loading ? <div style={{ padding: 24 }}>{tc("loading")}</div> : (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...TH, textAlign: "left" }}>{t("month")}</th>
                <th style={TH}>{t("paxInHouse")}</th>
                <th style={TH}>{t("paxExternal")}</th>
                <th style={TH}>{t("ticket")}</th>
                <th style={TH}>{t("paxTotal")}</th>
                {COMIDAS.map(c => <th key={c} style={TH}>{t(`meal_${c}`)}</th>)}
                <th style={TH}>{t("gross")}</th>
                <th style={TH} title={t("discountHint")}>{t("discount")}</th>
                <th style={TH}>{t("foodExternal")}</th>
                <th style={TH}>{t("food")}</th>
                <th style={TH}>{t("beverage")}</th>
                <th style={TH}>{t("total")}</th>
                <th style={{ ...TH, color: "var(--text-secondary)" }}
                  title={t("serviceHint")}>{t("service")}</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...TD, textAlign: "left", fontWeight: 600 }}>{MONTHS[i]}</td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>{ent(f.pax)}</td>
                  <td style={TD}>
                    <input className="fin-input mono" type="number" value={paxExt[i]} disabled={bloqueado}
                      onChange={e => { const v = [...paxExt]; v[i] = e.target.value; setPaxExt(v); setDirty(true); }}
                      style={{ ...inp, width: 76 }} />
                  </td>
                  <td style={TD}>
                    <input className="fin-input mono" type="number" value={ticket[i]} disabled={bloqueado}
                      onChange={e => { const v = [...ticket]; v[i] = e.target.value; setTicket(v); setDirty(true); }}
                      style={{ ...inp, width: 76 }} />
                  </td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>{ent(f.pax + n(paxExt[i]))}</td>
                  {COMIDAS.map(c => <td key={c} style={TD}>{usd(f[c])}</td>)}
                  <td style={TD}>{usd(f.bruto)}</td>
                  <td style={{ ...TD, color: f.desc ? "var(--negative, #C0392B)" : "var(--text-secondary)" }}>
                    {f.desc ? `−${usd(f.desc)}` : usd(0)}
                  </td>
                  <td style={TD}>{usd(f.foodExt)}</td>
                  <td style={{ ...TD, fontWeight: 600 }}>{usd(f.food)}</td>
                  <td style={TD}>{usd(f.bev)}</td>
                  <td style={{ ...TD, fontWeight: 700 }}>{usd(f.total)}</td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>{usd(f.sc)}</td>
                </tr>
              ))}
              <tr style={{ borderTop: "2px solid var(--border-medium)", fontWeight: 700 }}>
                <td style={{ ...TD, textAlign: "left" }}>{tc("total")}</td>
                <td style={TD}>{ent(tot.pax)}</td>
                <td style={TD}>{ent(paxExt.reduce((a, v) => a + n(v), 0))}</td>
                <td style={TD}>—</td>
                <td style={TD}>{ent(tot.pax + paxExt.reduce((a, v) => a + n(v), 0))}</td>
                {COMIDAS.map(c => (
                  <td key={c} style={TD}>{usd(filas.reduce((a, f) => a + f[c], 0))}</td>
                ))}
                <td style={TD}>{usd(tot.bruto)}</td>
                <td style={{ ...TD, color: tot.desc ? "var(--negative, #C0392B)" : undefined }}>
                  {tot.desc ? `−${usd(tot.desc)}` : usd(0)}
                </td>
                <td style={TD}>{usd(tot.foodExt)}</td>
                <td style={TD}>{usd(tot.food)}</td>
                <td style={TD}>{usd(tot.bev)}</td>
                <td style={TD}>{usd(tot.total)}</td>
                <td style={{ ...TD, color: "var(--text-secondary)" }}>{usd(tot.sc)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
