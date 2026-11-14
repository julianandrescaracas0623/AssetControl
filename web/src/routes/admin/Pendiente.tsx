import { Construction } from 'lucide-react'
import { useLocation } from 'react-router'

import { buscarEnNav } from '@/components/app/admin-nav'

// Pantalla de administración que aún no se construye: dice qué la trae.
export default function Pendiente() {
  const { pathname } = useLocation()
  const encontrado = buscarEnNav(pathname)
  const titulo = encontrado?.item.titulo ?? 'Administración'
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{titulo}</h1>
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
        <span className="flex size-10 items-center justify-center rounded-lg bg-muted" aria-hidden="true">
          <Construction className="size-5" />
        </span>
        <p className="font-medium">Pantalla en preparación</p>
        <p className="max-w-sm text-sm text-muted-foreground">Llega con {encontrado?.item.llega ?? 'una spec posterior'}.</p>
      </div>
    </div>
  )
}
