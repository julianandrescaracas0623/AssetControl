import { Navigate, type RouteObject } from 'react-router'

import App from './App'
import AdminShell from './components/app/AdminShell'
import FichaActivo from './routes/admin/FichaActivo'
import AdminInicio from './routes/admin/Inicio'
import Pendiente from './routes/admin/Pendiente'
import RequiereAdmin from './routes/admin/RequiereAdmin'
import ContarInicio from './routes/contar/Inicio'
import Componentes from './routes/dev/Componentes'
import Login from './routes/Login'
import Maqueta from './routes/Maqueta'
import NoEncontrado from './routes/NoEncontrado'

// Rutas de la web (spec 001b, T3). /admin y /contar son maquetas con datos
// ficticios hasta que cada spec conecte la API.
export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/admin" replace /> },
  { path: '/health', element: <App /> },
  { path: '/login', element: <Login /> },
  { path: '/dev/componentes', element: <Componentes /> },
  {
    path: '/admin',
    element: <RequiereAdmin />,
    children: [
      {
        element: <AdminShell />,
        children: [
          { index: true, element: <AdminInicio /> },
          ...['activos', 'activos/nuevo', 'ubicaciones', 'categorias', 'sesiones', 'discrepancias', 'valor', 'usuarios'].map(
            (path) => ({ path, element: <Pendiente /> }),
          ),
          { path: 'activos/:codigo', element: <FichaActivo /> },
        ],
      },
    ],
  },
  {
    element: <Maqueta />,
    children: [{ path: '/contar', children: [{ index: true, element: <ContarInicio /> }] }],
  },
  { path: '*', element: <NoEncontrado /> },
]
