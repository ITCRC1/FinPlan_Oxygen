"use client";
/**
 * La celda de dinero: se lee con formato, se edita en crudo.
 *
 * Owner, 2026-10-08: *«que todo esto tenga formato profesional… que se vean
 * bien con el signo de dólares y formateado»*.
 *
 * ## La tensión que resuelve
 *
 * `lib/fmt.ts` tenía dos funciones y una decisión escrita: `money2` es «sin
 * separador de miles, para que sea editable/parseable». Era cierto —un campo
 * que muestra `90,766.98` pelea con el cursor mientras se escribe— pero dejaba
 * la grilla entera en `90766.98` al lado de totales en `$1,074,207.63`. Doce
 * columnas de números sin separador son ilegibles justo donde más importa:
 * nadie distingue 90.766 de 907.669 de un vistazo.
 *
 * La salida no es elegir una de las dos. Es que **sea cada una cuando toca**:
 *
 *     sin foco  →  $90,766.98     se lee
 *     con foco  →  90766.98       se escribe, y queda seleccionado
 *     al salir  →  se normaliza a dos decimales y vuelve a formatearse
 *
 * ## El cero se muestra como raya
 *
 * Igual que `fmtUsd` en los totales. Una grilla de doce meses con `0.00`
 * repetido es ruido que tapa los meses que sí tienen plata — y esta propiedad
 * tiene líneas enteras en cero con todo derecho. Al entrar a la celda aparece
 * `0.00` seleccionado, así que escribir encima sigue siendo un solo gesto.
 *
 * ## Por qué no `type="number"`
 *
 * Porque trae las flechitas del navegador, que en una grilla financiera de
 * doce columnas se ven mal y se disparan con la rueda del mouse estando sobre
 * la celda — un scroll distraído cambia un presupuesto. Con `text` +
 * `inputMode="decimal"` el teclado del móvil sigue siendo numérico.
 *
 * ## El negativo va en rojo, tambien editando
 *
 * Owner, 2026-10-08: *«todos los negativos deben estar en rojo»*. La regla vale
 * igual en una celda que se escribe: un gasto cargado con signo cambiado se ve
 * al instante en vez de aparecer tres pantallas despues, en un total que no
 * cuadra.
 *
 * ⚠️ **`onPaste` se pasa tal cual.** `tests/test_planning_se_pega_desde_excel`
 * exige que toda grilla editable acepte un bloque de Excel; este componente no
 * lo resuelve por su cuenta porque sólo la pantalla sabe a qué fila y mes
 * corresponde lo que se soltó.
 */
import { useState } from "react";
import { fmtUsd, money2 } from "@/lib/fmt";
import { esNegativo } from "./Monto";

export default function InputMoneda({
  value, onChange, disabled, readOnly, onPaste, style, className, title,
}: {
  /** El monto en crudo, como lo guarda la pantalla: "90766.98". */
  value: string | number;
  /** Recibe el valor ya normalizado a dos decimales al salir de la celda. */
  onChange: (v: string) => void;
  disabled?: boolean;
  readOnly?: boolean;
  onPaste?: React.ClipboardEventHandler<HTMLInputElement>;
  style?: React.CSSProperties;
  className?: string;
  title?: string;
}) {
  const [foco, setFoco] = useState(false);
  const crudo = String(value ?? "");

  // Sin foco se lee con signo y separador; con foco, el numero pelado.
  const mostrado = foco ? crudo : fmtUsd(crudo);

  return (
    <input
      className={className ?? "fin-input mono"}
      type="text"
      inputMode="decimal"
      value={mostrado}
      disabled={disabled}
      readOnly={readOnly}
      title={title}
      onFocus={e => {
        if (readOnly) return;
        setFoco(true);
        // El select va despues del re-render: en este instante la celda todavia
        // muestra el texto formateado y seleccionarlo dejaria el signo adentro.
        const el = e.currentTarget;
        setTimeout(() => { try { el.select(); } catch { /* ya no esta */ } }, 0);
      }}
      onBlur={e => {
        setFoco(false);
        const v = money2(e.target.value);
        if (v !== crudo) onChange(v);
      }}
      onChange={e => onChange(e.target.value)}
      onPaste={onPaste}
      style={{
        // ⚠️ Un ancho minimo, o la columna corta el numero. Un `width: 100%`
        // dentro de una celda no le da ancho propio a la columna, asi que al
        // pasar de `90766.98` a `-$90,766.98` —tres caracteres mas— el texto
        // se corta y el ultimo digito desaparece sin que nada lo avise. 108px
        // entran `-$200,000.00` a 13px monoespaciado. La tabla vive en
        // `fin-scroll-x`, asi que crecer de ancho no rompe nada.
        minWidth: 108,
        textAlign: "right",
        fontVariantNumeric: "tabular-nums",
        // El rojo se calcula sobre el CRUDO: con foco el texto es "-1234.56" y
        // sin foco "-$1,234.56", y las dos formas tienen que verse igual.
        ...(esNegativo(crudo) ? { color: "var(--negative, #EF5350)" } : {}),
        ...style,
      }}
    />
  );
}
