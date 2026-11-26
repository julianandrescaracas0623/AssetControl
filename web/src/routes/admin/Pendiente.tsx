import { Construction } from 'lucide-react'
import { useLocation } from 'react-router'

import { buscarEnNav } from '@/components/app/app-nav'
import { EncabezadoPagina, Estado } from '@/components/kit'

// Pantalla de administración que aún no se construye: dice qué la trae.
// Spec 016, T9: encabezado y estado vacío del kit.
export default function Pendiente() {
  const { pathname } = useLocation()
  const encontrado = buscarEnNav(pathname)
  const titulo = encontrado?.item.titulo ?? 'Administración'
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina titulo={titulo} />
      <Estado.Vacio
        icono={<Construction />}
        titulo="Pantalla en preparación"
        descripcion={`Llega con ${encontrado?.item.llega ?? 'una spec posterior'}.`}
        className="py-16"
      />
    </div>
  )
}
