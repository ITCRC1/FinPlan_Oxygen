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
    const foodHosp = COMIDAS.reduce((a, c) => a + porComida[c], 0);
    const foodExt = n(paxExt[i]) * n(ticket[i]);
    const pre = foodHosp + foodExt;
    const sc = pre * (n(servicio) / 100);
    const food = pre + sc;
    const bev = food * (n(bevPct) / 100);
    return { mes: i, pax, ...porComida, foodHosp, foodExt, pre, sc, food, bev, total: food + bev };
  });
  const tot = filas.reduce((a, f) => ({
    pax: a.pax + f.pax, foodHosp: a.foodHosp + f.foodHosp, foodExt: a.foodExt + f.foodExt,
    sc: a.sc + f.sc, food: a.food + f.food, bev: a.bev + f.bev, total: a.total + f.total,
  }), { pax: 0, foodHosp: 0, foodExt: 0, sc: 0, food: 0, bev: 0, total: 0 });

  const bloqueado = !!data?.locked;

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
        <select className="fin-input" value={scenarioId}
          onChange={e => setScenarioId(e.target.value)} style={{ padding: "6px 10px", fontSize: 13 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={guardar} disabled={!dirty || saving || bloqueado} style={btn(dirty && !saving && !bloqueado)}>
          {saving ? tc("saving") : tc("save")}
        </button>
        <button onClick={alCheckbook} disabled={saving || bloqueado || dirty}
          title={t("moveHint")} style={btn(!saving && !bloqueado && !dirty)}>
          {t("moveToCheckbook")}
        </button>
        <button onClick={recalcular} disabled={recalc || bloqueado} style={btn(!recalc && !bloqueado)}>
          {recalc ? tc("recalc.running") : t("recalc")}
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
        {campo(t("serviceCharge"), servicio, setServicio, "%")}
        {campo(t("bevPctFood"), bevPct, setBevPct, "%")}
      </div>

      {loading ? <div style={{ padding: 24 }}>{tc("loading")}</div> : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...TH, textAlign: "left" }}>{t("month")}</th>
                <th style={TH}>{t("paxInHouse")}</th>
                <th style={TH}>{t("paxExternal")}</th>
                <th style={TH}>{t("ticket")}</th>
                <th style={TH}>{t("paxTotal")}</th>
                {COMIDAS.map(c => <th key={c} style={TH}>{t(`meal_${c}`)}</th>)}
                <th style={TH}>{t("foodExternal")}</th>
                <th style={TH}>{t("service")}</th>
                <th style={TH}>{t("food")}</th>
                <th style={TH}>{t("beverage")}</th>
                <th style={TH}>{t("total")}</th>
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
                  <td style={TD}>{usd(f.foodExt)}</td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>{usd(f.sc)}</td>
                  <td style={{ ...TD, fontWeight: 600 }}>{usd(f.food)}</td>
                  <td style={TD}>{usd(f.bev)}</td>
                  <td style={{ ...TD, fontWeight: 700 }}>{usd(f.total)}</td>
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
                <td style={TD}>{usd(tot.foodExt)}</td>
                <td style={TD}>{usd(tot.sc)}</td>
                <td style={TD}>{usd(tot.food)}</td>
                <td style={TD}>{usd(tot.bev)}</td>
                <td style={TD}>{usd(tot.total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
