// Marca de la consola (spec 017, T8; R11): `MarcoAcceso` ya pinta el logo y «AssetControl»;
// este rótulo completa «AssetControl Dev», igual que el shell (PlataformaShell), y así
// distingue la consola de desarrolladores del acceso de una clínica. El espacio inicial no
// se ve (inicio de un elemento flex) pero deja «AssetControl Dev» en el texto accesible;
// `-ml-1` acerca la palabra al ancho de un espacio dentro del `gap` del marco.
export function MarcaPlataforma() {
  return <span className="-ml-1 text-titulo-seccion tracking-tight">{' '}Dev</span>
}
