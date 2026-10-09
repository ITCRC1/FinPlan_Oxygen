"use client";
/**
 * Un monto en pantalla: si es negativo, va en rojo.
 *
 * Owner, 2026-10-08: *«todos los negativos deben estar en rojo»*. Es la regla
 * del design system (CLAUDE.md §26.9: *«NÚMERO NEGATIVO: siempre en rojo»*) y
 * no se estaba cumpliendo fuera de las varianzas.
 *
 * ## Por qué recibe el TEXTO y no el número
 *
 * Esta aplicación tiene cerca de cuarenta formateadores de dinero: `fmtUsd` de
 * `lib/fmt`, y uno propio en casi cada pantalla —algunos con paréntesis
 * contables `($1,234)`, otros sin decimales, otros con `—` para el vacío—.
 * Pedirle el número a cada sitio obligaría a reescribir los cuarenta y a elegir
 * un formato único, que es una discusión aparte y mucho más riesgosa.
 *
 * Recibiendo el texto ya armado, el envoltorio funciona con todos sin tocar
 * ninguno: el negativo se reconoce por cómo se escribe, que es justamente lo
 * único que los cuarenta tienen en común.
 *
 *     -$1,234.56    ($1,234)    −1,234    -1,234.56
 *
 * ## Qué NO hace
 *
 * No formatea. Si el texto llega mal armado, llega mal armado y se ve — este
 * componente no lo tapa. Y no colorea el cero ni la raya: un cero en rojo es
 * ruido, y `—` no es un número.
 */
import type { ReactNode } from "react";

/** ¿El texto de un monto representa un negativo? */
export function esNegativo(texto: ReactNode): boolean {
  if (typeof texto !== "string" && typeof texto !== "number") return false;
  const t = String(texto).trim();
  if (!t) return false;
  // El guion normal, el menos tipográfico, y el paréntesis contable.
  // ⚠️ La raya larga «—» (vacío) NO entra: no es un número.
  if (t.startsWith("-") || t.startsWith("−")) return true;
  if (t.startsWith("(") && t.endsWith(")")) return true;
  // "$-1,234.56": lo que devolvia `fmtUsd` antes del 2026-10-08. Se reconoce
  // igual, porque hay cifras guardadas en reportes viejos con esa forma.
  return /^[$€£₡]\s*[-−]/.test(t);
}

export default function Monto({ children, style, className, title }: {
  children: ReactNode;
  style?: React.CSSProperties;
  className?: string;
  title?: string;
}) {
  const neg = esNegativo(children);
  if (!neg && !style && !className && !title) return <>{children}</>;
  return (
    <span className={className} title={title}
      style={neg ? { color: "var(--negative, #EF5350)", ...style } : style}>
      {children}
    </span>
  );
}
