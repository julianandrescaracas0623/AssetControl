// Tipos de las cifras que entrega el servidor (spec 001b, R10). El valor
// actual (tiempo real, R7) y el informe congelado (R4, R9) son tipos
// distintos: un componente de uno no acepta el otro, y nunca comparten tarjeta.

export interface Cifra {
  valor: string
  unidades: number
}

export interface InformeCongelado {
  readonly fuente: 'informe_congelado'
  sesion: string
  corte: string
  encontrado: Cifra
  noEncontrado: Cifra & { enReparacion?: number }
  total: Cifra
}

export interface ValorActual {
  readonly fuente: 'valor_actual'
  valor: string
  activos: number
  consultadoA: string
}
