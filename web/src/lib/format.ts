// Formato de presentación (docs/08 §2.3). Las cifras vienen del servidor como
// texto decimal (NUMERIC(14,2)); se formatean sin pasar por float para no
// perder precisión. Nunca se calcula aquí ningún total.

const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/

function agruparMiles(entero: string): string {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** "1234567.8" → "$ 1.234.567,80" (es-CO). */
export function formatCOP(valor: string): string {
  const partes = DECIMAL.exec(valor)
  if (!partes) throw new Error(`Valor de dinero inválido: «${valor}»`)
  const [, signo, entero, decimales = ''] = partes
  const limpio = entero.replace(/^0+(?=\d)/, '')
  return `${signo}$ ${agruparMiles(limpio)},${decimales.padEnd(2, '0')}`
}

/** 1234567 → "1.234.567". */
export function formatEntero(n: number): string {
  return agruparMiles(String(Math.trunc(n)))
}

/** "1 unidad", "2 unidades", "1.250 unidades". */
export const formatUnidades = (n: number) => `${formatEntero(n)} ${n === 1 ? 'unidad' : 'unidades'}`
