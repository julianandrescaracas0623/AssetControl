import type { RouteObject } from 'react-router'

import App from './App'
import AdminShell from './components/app/AdminShell'
import Activos from './routes/admin/Activos'
import FichaActivo from './routes/admin/FichaActivo'
import Informe from './routes/admin/Informe'
import AdminInicio from './routes/admin/Inicio'
import Pendiente from './routes/admin/Pendiente'
import RegistrarActivo from './routes/admin/RegistrarActivo'
import RequiereAdmin from './routes/admin/RequiereAdmin'
import Usuarios from './routes/admin/Usuarios'
import Alta from './routes/contar/Alta'
import Escanear from './routes/contar/Escanear'
import Escribir from './routes/contar/Escribir'
import Historial from './routes/contar/Historial'
import ContarInicio from './routes/contar/Inicio'
import NoConfirmado from './routes/contar/NoConfirmado'
import Pendientes from './routes/contar/Pendientes'
import Verificado from './routes/contar/Verificado'
import Verificar from './routes/contar/Verificar'
import Componentes from './routes/dev/Componentes'
import InicioPorRol from './routes/InicioPorRol'
import Invitacion from './routes/Invitacion'
import Login from './routes/Login'
import Maqueta from './routes/Maqueta'
import NoEncontrado from './routes/NoEncontrado'
import RequiereSesion from './routes/RequiereSesion'
import Raiz from './routes/Raiz'

// Rutas de la web (spec 001b, T3; sesión y guardas de la spec 002b, T3). /admin y
// /contar exigen sesión; sus pantallas siguen siendo maquetas con datos ficticios
// hasta que cada spec conecte la API.
export const routes: RouteObject[] = [
  {
    element: <Raiz />,
    children: [
      { path: '/', element: <InicioPorRol /> },
      { path: '/health', element: <App /> },
      { path: '/login', element: <Login /> },
      { path: '/invitacion', element: <Invitacion /> },
      { path: '/dev/componentes', element: <Componentes /> },
      {
        element: <RequiereSesion />,
        children: [
          {
            path: '/admin',
            element: <RequiereAdmin />,
            children: [
              {
                element: <AdminShell />,
                children: [
                  { index: true, element: <AdminInicio /> },
                  { path: 'activos', element: <Activos /> },
                  { path: 'activos/nuevo', element: <RegistrarActivo /> },
                  { path: 'sesiones/:id/informe', element: <Informe /> },
                  { path: 'usuarios', element: <Usuarios /> },
                  ...['ubicaciones', 'categorias', 'sesiones', 'discrepancias', 'valor'].map(
                    (path) => ({ path, element: <Pendiente /> }),
                  ),
                  { path: 'activos/:codigo', element: <FichaActivo /> },
                ],
              },
            ],
          },
          {
            element: <Maqueta />,
            children: [
              {
                path: '/contar',
                children: [
                  { index: true, element: <ContarInicio /> },
                  { path: 'escanear', element: <Escanear /> },
                  { path: 'escribir', element: <Escribir /> },
                  { path: 'activo/:codigo', element: <Verificar /> },
                  { path: 'activo/:codigo/historial', element: <Historial /> },
                  { path: 'verificado/:codigo', element: <Verificado /> },
                  { path: 'no-confirmado/:codigo', element: <NoConfirmado /> },
                  { path: 'nuevo', element: <Alta /> },
                  { path: 'pendientes', element: <Pendientes /> },
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
