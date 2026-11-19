// Spec 016, D13 (R11): medidas fijas de imagen, en un solo lugar (las usa MarcoImagen y
// las reutiliza el logo de la T9). Valores por defecto fijados por el coordinator por
// indicación del humano; cambiar un tamaño es cambiarlo aquí.

export type VarianteImagen = 'foto' | 'logo' | 'logoCabecera'

/** Medidas de D13 (h-50 = 200 px, h-60 = 240 px, w-80 = 320 px, w-40 = 160 px, h-16 = 64 px, max-w-30 = 120 px). */
export const MEDIDAS_IMAGEN: Record<VarianteImagen, { caja: string; imagen: string; ajuste: 'object-cover' | 'object-contain' }> = {
  foto: { caja: 'h-50 w-full max-w-full md:h-60 md:w-80', imagen: 'size-full', ajuste: 'object-cover' },
  logo: { caja: 'h-16 w-40 max-w-full bg-muted p-1', imagen: 'size-full', ajuste: 'object-contain' },
  logoCabecera: { caja: 'inline-flex h-8 max-w-30 items-center', imagen: 'h-full w-auto max-w-full', ajuste: 'object-contain' },
}
