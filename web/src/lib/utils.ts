import { createCn } from 'cn/config'

// Spec 016, T3: la escala tipográfica nombrada de index.css (text-titulo-pagina,
// text-cuerpo, text-cifra…) es tamaño de letra. Sin declararla, la fusión de clases la
// tomaba por un color y la borraba al lado de text-muted-foreground o text-warning.
// (components/ui importa cn de 'cn' sin esta extensión: ahí no se mezclan tamaños propios.)
export const cn = createCn({
  extend: {
    classGroups: {
      'font-size': [{ text: ['titulo-pagina', 'titulo-seccion', 'cuerpo', 'etiqueta', 'cifra', 'codigo'] }],
    },
  },
})
