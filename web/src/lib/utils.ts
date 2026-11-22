import { createCn } from 'cn/config'

// Spec 016, T3: la escala tipográfica nombrada de index.css (text-titulo-pagina,
// text-cuerpo, text-cifra…) es tamaño de letra. Sin declararla, la fusión de clases la
// tomaba por un color y la borraba al lado de text-muted-foreground o text-warning.
// Spec 016, T10 (Deuda T2 b, T3 f): las alturas de densidad (h-control, h-fila, h-accion,
// sus min-h-*) y gap-separacion se fusionan como alturas y separaciones: quien usa el kit
// puede cambiarlas (h-control + h-12 → h-12). size-control NO se declara a propósito:
// «size» choca con «h» y borraría h-control, y el h-8 de shadcn (que el CSS ordena después
// de size-*) dejaría el botón en 32 px (visto en el navegador en la T10). El orden del
// CSS lo vigila cascada.node.test.ts y la altura real, el informe de QA en navegador.
// (components/ui importa cn de 'cn' sin esta extensión: ahí no se mezclan tamaños propios;
// el kit pone la escala tipográfica en un elemento propio cuando envuelve un componente de ui.)
const ALTURAS = ['control', 'fila', 'accion']

export const cn = createCn({
  extend: {
    classGroups: {
      'font-size': [{ text: ['titulo-pagina', 'titulo-seccion', 'cuerpo', 'etiqueta', 'cifra', 'codigo'] }],
      h: [{ h: ALTURAS }],
      'min-h': [{ 'min-h': ALTURAS }],
      gap: [{ gap: ['separacion'] }],
    },
  },
})
