import { Cifra, CifrasCongeladas } from '@/components/kit'
import type { InformeCongelado, ValorActual } from '@/lib/cifras'
import { formatCOP, formatEntero, formatUnidades } from '@/lib/format'

// R7/R10: el informe congelado y el valor actual viven en tarjetas distintas,
// con rótulos distintos. Las cifras llegan del servidor; aquí no se suma nada.
// Spec 016, T3: conservan su API y delegan en CifrasCongeladas y Cifra (en vivo) del
// kit, que ponen los rótulos «Informe congelado» y «Tiempo real · No es el informe».

export function ThreeFiguresCard({
  informe,
  accion,
  titulo = 'Último informe cerrado',
}: {
  informe: InformeCongelado
  accion?: React.ReactNode
  titulo?: string
}) {
  return (
    <CifrasCongeladas
      titulo={titulo}
      meta={`${informe.sesion} · corte ${informe.corte}`}
      accion={accion}
      cifras={[
        { rotulo: 'Encontrado', tono: 'exito', valor: formatCOP(informe.encontrado.valor), detalle: formatUnidades(informe.encontrado.unidades) },
        { rotulo: 'No encontrado', tono: 'error', valor: formatCOP(informe.noEncontrado.valor), detalle: formatUnidades(informe.noEncontrado.unidades) },
        { rotulo: 'Total registrado', tono: 'neutro', valor: formatCOP(informe.total.valor), detalle: formatUnidades(informe.total.unidades) },
      ]}
    />
  )
}

export function LiveValueCard({ valor }: { valor: ValorActual }) {
  return (
    <Cifra
      fuente="en_vivo"
      region
      rotulo="Valor actual"
      valor={formatCOP(valor.valor)}
      contexto={`COP · ${formatEntero(valor.activos)} activos · ${valor.consultadoA}`}
    />
  )
}
