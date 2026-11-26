import { Lock } from 'lucide-react'
import { Link, Outlet } from 'react-router'

import { Boton, EncabezadoPagina, Estado } from '@/components/kit'
import { RAIZ_APP } from '@/lib/rutas'
import { useSesion } from '@/lib/sesion'

// Pantallas exclusivas del admin (spec 002b, T3; R6. Spec 020, T3: R3, req. 8): Usuarios,
// Empresa, Ubicaciones, Categorías, Valor e Informe. Va dentro del marco compartido: el
// contador lo conserva con su menú y ve «Sin permiso» con salida a su Inicio.
// Presentación: la API responde 403 a un contador en cualquier endpoint de admin.
export default function RequiereAdmin() {
  const { sesion } = useSesion()
  if (sesion?.rol === 'admin') return <Outlet />
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina titulo="No tienes permiso para ver esto" descripcion="Esta parte es solo para administradores de la clínica." />
      <Estado.Vacio
        icono={<Lock />}
        titulo="Pantalla del administrador"
        descripcion="Si necesitas algo de aquí, pídeselo al administrador de la clínica."
        accion={
          <Boton asChild>
            <Link to={RAIZ_APP}>Ir al inicio</Link>
          </Boton>
        }
        className="py-16"
      />
    </div>
  )
}
