// Proporción de una barra (spec 010, T4): solo para dibujar; la cifra visible es la del servidor.

/** Largo relativo de la barra en % (0–100). Solo para dibujar. */
export function proporcion(valor: string | null, maximo: number): number {
  if (valor === null || maximo <= 0) return 0
  const n = Number(valor)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.max(1, Math.min(100, (n / maximo) * 100))
}
