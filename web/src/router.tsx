import type { RouteObject } from 'react-router'

import App from './App'
import AppShell from './components/app/AppShell'
import Activos from './routes/admin/Activos'
import FichaActivo from './routes/admin/FichaActivo'
import RutaDetalleSesion from './routes/admin/DetalleSesion'
import Discrepancias from './routes/admin/Discrepancias'
import EmpresaPagina from './routes/admin/Empresa'
import Sesiones from './routes/admin/Sesiones'
import Informe from './routes/admin/Informe'
import RegistrarActivo from './routes/admin/RegistrarActivo'
import RequiereAdmin from './routes/admin/RequiereAdmin'
import Categorias from './routes/admin/Categorias'
import Ubicaciones from './routes/admin/Ubicaciones'
import Usuarios from './routes/admin/Usuarios'
import Valor from './routes/admin/Valor'
import Escanear from './routes/contar/Escanear'
import EspacioConteo from './routes/contar/Escritorio'
import Escribir from './routes/contar/Escribir'
import Verificar from './routes/contar/Verificar'
import { AliasAdmin, AltaConteo, HistorialConteo, InicioApp, InicioConteo, PendientesConteo } from './routes/app/rutasApp'
import InicioPorRol from './routes/InicioPorRol'
import Invitacion from './routes/Invitacion'
import Login from './routes/Login'
import Maqueta from './routes/Maqueta'
import NoEncontrado from './routes/NoEncontrado'
import CambiarContrasena from './routes/CambiarContrasena'
import NuevaContrasena from './routes/NuevaContrasena'
import RequiereSesion from './routes/RequiereSesion'
import Raiz from './routes/Raiz'
import RecuperarContrasena from './routes/RecuperarContrasena'
import Entrar from './routes/plataforma/Entrar'
import PlataformaShell from './routes/plataforma/PlataformaShell'
import RaizPlataforma from './routes/plataforma/RaizPlataforma'
import RequiereDesarrollador from './routes/plataforma/RequiereDesarrollador'
import { ErrorModulo, InicioPlataforma, RutaModulo } from './routes/plataforma/RutaModulo'

// Rutas de la web (spec 001b, T3; sesión y guardas de la spec 002b, T3). /app y
// /contar exigen sesión; las pantallas que aún son maqueta lo dicen con su banda.
// Spec 020, T3 (R1–R3, R11): /app es el marco compartido de los dos roles; solo las
// pantallas exclusivas del admin van bajo RequiereAdmin. /admin/** es un alias que
// redirige a /app/** con la misma query. En el computador, /contar lleva a /app; el
// espacio de conteo (escanear, escribir, activo/:codigo) no redirige. T5: en el computador
// /contar/nuevo lleva al alta del marco (/app/activos/nuevo) con la misma query. T6: en el
// computador /contar/pendientes lleva al detalle de la sesión abierta (con su ?ubicacion=)
// y el historial del activo, a su ficha del marco.
export const routes: RouteObject[] = [
  // Spec 017, T8: consola de plataforma, fuera de la Raiz de la clínica (cliente de
  // consultas y sesión propios). Las pantallas de cada módulo salen de su registro
  // (routes/plataforma/modulos.ts) y se cargan al abrirlas; el shell no cambia.
  {
    path: '/plataforma',
    element: <RaizPlataforma />,
    children: [
      { path: 'entrar', element: <Entrar /> },
      {
        element: <RequiereDesarrollador />,
        children: [
          {
            element: <PlataformaShell />,
            children: [
              { index: true, element: <InicioPlataforma /> },
              { path: ':modulo/*', element: <RutaModulo />, errorElement: <ErrorModulo /> },
            ],
          },
        ],
      },
    ],
  },
  {
    element: <Raiz />,
    children: [
      { path: '/', element: <InicioPorRol /> },
      { path: '/health', element: <App /> },
      { path: '/login', element: <Login /> },
      { path: '/invitacion', element: <Invitacion /> },
      { path: '/recuperar', element: <RecuperarContrasena /> },
      { path: '/restablecer', element: <NuevaContrasena /> },
      // SEC-07: la página de componentes (datos de ejemplo) solo existe en desarrollo; la
      // condición es la misma que la del módulo de prueba de la consola (modulos.ts).
      ...(import.meta.env.DEV
        ? [
            {
              path: '/dev/componentes',
              lazy: async () => ({ Component: (await import('./routes/dev/Componentes')).default }),
            },
          ]
        : []),
      {
        element: <RequiereSesion />,
        children: [
          // Spec 017, T4 (R26): única pantalla mientras la cuenta deba cambiar la contraseña.
          { path: '/cambiar-contrasena', element: <CambiarContrasena /> },
          {
            path: '/app',
            element: <AppShell />,
            children: [
              { index: true, element: <InicioApp /> },
              { path: 'activos', element: <Activos /> },
              { path: 'activos/nuevo', element: <RegistrarActivo /> },
              { path: 'sesiones', element: <Sesiones /> },
              { path: 'discrepancias', element: <Discrepancias /> },
              { path: 'sesiones/:id', element: <RutaDetalleSesion /> },
              { path: 'activos/:codigo', element: <FichaActivo /> },
              {
                element: <RequiereAdmin />,
                children: [
                  { path: 'sesiones/:id/informe', element: <Informe /> },
                  { path: 'usuarios', element: <Usuarios /> },
                  { path: 'empresa', element: <EmpresaPagina /> },
                  { path: 'ubicaciones', element: <Ubicaciones /> },
                  { path: 'categorias', element: <Categorias /> },
                  { path: 'valor', element: <Valor /> },
                ],
              },
            ],
          },
          { path: '/admin/*', element: <AliasAdmin /> },
          {
            element: <Maqueta />,
            children: [
              {
                path: '/contar',
                children: [
                  { index: true, element: <InicioConteo /> },
                  // Spec 015, T8: en escritorio estas tres son un solo espacio de dos
                  // paneles; en teléfono, las pantallas de siempre.
                  {
                    element: <EspacioConteo />,
                    children: [
                      { path: 'escanear', element: <Escanear /> },
                      { path: 'escribir', element: <Escribir /> },
                      { path: 'activo/:codigo', element: <Verificar /> },
                    ],
                  },
                  { path: 'activo/:codigo/historial', element: <HistorialConteo /> },
                  { path: 'nuevo', element: <AltaConteo /> },
                  { path: 'pendientes', element: <PendientesConteo /> },
                ],
              },
            ],
          },
        ],
      },
      { path: '*', element: <NoEncontrado /> },
    ],
  },
]
