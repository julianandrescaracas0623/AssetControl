import { Building2, EllipsisVertical, Pencil, Plus, Power, PowerOff, Users } from 'lucide-react'
import { useState } from 'react'
import { Link, Route, Routes } from 'react-router'
import { toast } from 'sonner'

import {
  Boton,
  type ColumnaTabla,
  Confirmar,
  EncabezadoPagina,
  Filtro,
  Insignia,
  Menu,
  type OpcionMenu,
  TablaDatos,
} from '@/components/kit'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatEntero } from '@/lib/format'

import { useModulos } from '../../modulos'
import { type EmpresaPlataforma, filtrarEmpresas, type FiltroEstado, rutaUsuarios, useCambiarEstadoEmpresa, useEmpresas } from './api'
import { EditarEmpresa } from './EditarEmpresa'
import NuevaEmpresa from './NuevaEmpresa'

// Módulo Empresas de la consola (spec 017, T9; R16–R22, R38, R40; CU-03, CU-05, CU-06).
// - Lista: buscador por nombre (filtra al escribir) y filtro de estado; tabla a 1440 px y
//   tarjetas a 375 px (TablaDatos). Solo identidad y conteos (R21): nunca datos de negocio.
//   Una empresa con 0 admins activos lleva «Sin admin activo».
// - Por fila: «Editar» (C1/T14: ficha y logo, EditarEmpresa; también con doble clic o Enter
//   sobre la fila, ajuste T15b), «Ver usuarios» (si el módulo
//   Usuarios está habilitado) y «Desactivar» o «Reactivar», siempre con Confirmar que nombra la
//   empresa y el efecto (R40).
// - «Nueva empresa» abre el formulario único de alta (NuevaEmpresa; C1c).
// Esconder una acción no es seguridad: cada endpoint exige el token de plataforma.

const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })

const ESTADOS: { valor: FiltroEstado; etiqueta: string }[] = [
  { valor: 'activas', etiqueta: 'Activas' },
  { valor: 'desactivadas', etiqueta: 'Desactivadas' },
  { valor: 'todas', etiqueta: 'Todas' },
]

function EstadoEmpresa({ activa }: { activa: boolean }) {
  return activa ? (
    <Insignia tono="exito">Activa</Insignia>
  ) : (
    <Insignia tono="neutro" icono={<PowerOff aria-hidden="true" />}>
      Desactivada
    </Insignia>
  )
}

function Nombre({ empresa }: { empresa: EmpresaPlataforma }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="break-words">{empresa.nombre}</span>
      {empresa.n_admins_activos === 0 && <Insignia tono="aviso">Sin admin activo</Insignia>}
    </span>
  )
}

const COLUMNAS: ColumnaTabla<EmpresaPlataforma>[] = [
  { id: 'nombre', encabezado: 'Empresa', principal: true, celda: (e) => <Nombre empresa={e} />, clase: 'min-w-56' },
  { id: 'estado', encabezado: 'Estado', celda: (e) => <EstadoEmpresa activa={e.activa} /> },
  { id: 'creada', encabezado: 'Creada', celda: (e) => fecha.format(new Date(e.creado_en)), clase: 'whitespace-nowrap' },
  { id: 'usuarios', encabezado: 'Usuarios activos', tipo: 'cifra', celda: (e) => formatEntero(e.n_membresias_activas) },
  { id: 'admins', encabezado: 'Admins activos', tipo: 'cifra', celda: (e) => formatEntero(e.n_admins_activos) },
  {
    id: 'logo',
    encabezado: 'Logo',
    celda: (e) => (e.tiene_logo ? 'Sí' : <span className="text-muted-foreground">Sin logo</span>),
  },
]

type Pendiente = { empresa: EmpresaPlataforma; activa: boolean }

function Lista() {
  const empresas = useEmpresas()
  const modulos = useModulos()
  const cambiar = useCambiarEstadoEmpresa()
  const [busqueda, setBusqueda] = useState('')
  const [estado, setEstado] = useState<FiltroEstado>('todas')
  const [pendiente, setPendiente] = useState<Pendiente | null>(null)
  const [editando, setEditando] = useState<EmpresaPlataforma | null>(null)
  const conUsuarios = modulos.data?.some((m) => m.id === 'usuarios') ?? false

  const filas = empresas.data ? filtrarEmpresas(empresas.data, busqueda, estado) : undefined
  const hayFiltros = busqueda.trim() !== '' || estado !== 'todas'
  const limpiar = () => {
    setBusqueda('')
    setEstado('todas')
  }

  const nueva = (
    <Boton icono={<Plus />} asChild>
      <Link to="nueva">Nueva empresa</Link>
    </Boton>
  )

  let vacio
  if (empresas.data && empresas.data.length === 0) {
    vacio = { titulo: 'Aún no hay empresas. Crea la primera.', descripcion: 'Cada empresa es una clínica con su primer admin.', accion: nueva, icono: <Building2 /> }
  } else if (busqueda.trim() !== '') {
    vacio = {
      titulo: 'No hay empresas con ese nombre',
      descripcion: estado === 'todas' ? 'Revisa cómo está escrito o busca por otra parte del nombre.' : 'Prueba con «Todas» o revisa cómo está escrito.',
      accion: <Boton variante="secundario" onClick={limpiar}>Limpiar filtros</Boton>,
    }
  } else {
    vacio = {
      titulo: estado === 'activas' ? 'No hay empresas activas' : 'No hay empresas desactivadas',
      accion: <Boton variante="secundario" onClick={limpiar}>Ver todas</Boton>,
    }
  }

  function confirmar() {
    if (!pendiente) return
    const { empresa, activa } = pendiente
    cambiar.mutate(
      { id: empresa.id, activa },
      {
        onSuccess: () => toast.success(activa ? `${empresa.nombre} reactivada` : `${empresa.nombre} desactivada`),
        onError: (error) => toast.error(mensajeDeError(error)),
      },
    )
  }

  function acciones(empresa: EmpresaPlataforma) {
    const opciones: OpcionMenu[] = [
      { etiqueta: 'Editar', icono: <Pencil aria-hidden="true" />, alElegir: () => setEditando(empresa) },
      ...(conUsuarios ? [{ etiqueta: 'Ver usuarios', icono: <Users aria-hidden="true" />, href: rutaUsuarios(empresa.id) }] : []),
      empresa.activa
        ? {
            etiqueta: 'Desactivar',
            icono: <PowerOff aria-hidden="true" />,
            peligro: true,
            separadorAntes: true,
            alElegir: () => setPendiente({ empresa, activa: false }),
          }
        : { etiqueta: 'Reactivar', icono: <Power aria-hidden="true" />, separadorAntes: true, alElegir: () => setPendiente({ empresa, activa: true }) },
    ]
    return (
      <Menu
        rotulo={empresa.nombre}
        opciones={opciones}
        disparador={<Boton variante="fantasma" soloIcono aria-label={`Acciones de ${empresa.nombre}`} icono={<EllipsisVertical />} />}
      />
    )
  }

  const total = empresas.data?.length ?? 0

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Empresas"
        descripcion="Las clínicas que usan AssetControl. Aquí ves su estado y cuántos usuarios tienen; nunca sus datos de negocio."
        acciones={nueva}
        claseAcciones="max-sm:w-full max-sm:[&_[data-slot=button]]:w-full"
      />
      <TablaDatos
        etiqueta="Empresas"
        columnas={COLUMNAS}
        filas={filas}
        claveFila={(e) => e.id}
        nombrarFilas
        cargando={empresas.isPending}
        error={
          empresas.isError
            ? {
                titulo: 'No se pudieron cargar las empresas',
                descripcion: mensajeDeError(empresas.error),
                onReintentar: () => void empresas.refetch(),
                reintentando: empresas.isFetching,
              }
            : null
        }
        vacio={vacio}
        onAbrirFila={setEditando}
        ayudaAbrirFila="Doble clic para editar"
        accionesFila={acciones}
        barra={{
          busqueda: { valor: busqueda, onCambio: setBusqueda, etiqueta: 'Buscar empresa por nombre', placeholder: 'Buscar por nombre', maxLength: 120 },
          filtros: (
            <Filtro
              etiqueta="Estado"
              unica
              opciones={ESTADOS.map((o) => ({
                ...o,
                conteo: empresas.data
                  ? o.valor === 'todas'
                    ? total
                    : empresas.data.filter((e) => e.activa === (o.valor === 'activas')).length
                  : undefined,
              }))}
              seleccion={estado === 'todas' ? [] : [estado]}
              onSeleccionChange={(s) => setEstado((s[0] as FiltroEstado | undefined) ?? 'todas')}
            />
          ),
          hayFiltros,
          onLimpiar: limpiar,
        }}
      />
      {editando && <EditarEmpresa empresa={editando} onCerrar={() => setEditando(null)} />}
      {pendiente && (
        <Confirmar
          abierto
          onAbiertoChange={(abierto) => {
            if (!abierto) setPendiente(null)
          }}
          titulo={pendiente.activa ? `¿Reactivar ${pendiente.empresa.nombre}?` : `¿Desactivar ${pendiente.empresa.nombre}?`}
          descripcion={
            pendiente.activa ? (
              <>
                Los usuarios activos de <strong>{pendiente.empresa.nombre}</strong> podrán volver a entrar con su correo y contraseña.
              </>
            ) : (
              <>
                Los usuarios de <strong>{pendiente.empresa.nombre}</strong> no podrán entrar. No se borra nada. Puedes reactivarla
                cuando quieras.
              </>
            )
          }
          textoConfirmar={pendiente.activa ? 'Sí, reactivar' : 'Sí, desactivar'}
          textoConfirmando={pendiente.activa ? 'Reactivando…' : 'Desactivando…'}
          peligro={!pendiente.activa}
          onConfirmar={confirmar}
        />
      )}
    </div>
  )
}

export default function Empresas() {
  return (
    <Routes>
      <Route index element={<Lista />} />
      <Route path="nueva" element={<NuevaEmpresa />} />
    </Routes>
  )
}
