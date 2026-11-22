// Spec 014 (T6, T7): «cuánto esperar» tras un 429, a partir de `ErrorApi.reintentarEn`.

/** «15 minutos», «1 minuto», «45 segundos»; `null` si no hay un número útil. */
export function textoEspera(segundos: number | undefined): string | null {
  if (segundos === undefined || !Number.isFinite(segundos) || segundos <= 0) return null
  if (segundos < 60) return segundos === 1 ? '1 segundo' : `${segundos} segundos`
  const minutos = Math.ceil(segundos / 60)
  return minutos === 1 ? '1 minuto' : `${minutos} minutos`
}
