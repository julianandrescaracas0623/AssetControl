// Datos FICTICIOS de las maquetas (spec 001b). No son datos de ninguna clínica
// real: "Clínica Demo", personas y cifras inventadas. Las cifras agregadas
// simulan lo que entregará el servidor (constitución: el servidor calcula) y
// cuadran entre sí como exige R9: cada desglose suma las tres cifras.
// Dinero como texto decimal (NUMERIC(14,2) llega como string; nunca float).

export const CLINICA = { nombre: 'Clínica Demo', ciudad: 'Cartago' }

export type EstadoActivo = 'activo' | 'en_reparacion' | 'dado_de_baja'
export type CondicionConteo = 'verificado' | 'pendiente' | 'otra_ubicacion'

export interface ActivoFicticio {
  codigo: string
  nombre: string
  categoria: string
  ubicacion: string
  estado: EstadoActivo
  conteo: CondicionConteo
  /** Precio de compra; solo lo recibe el admin (P13). */
  precio: string
  nuevoHoy?: boolean
}

export const CATEGORIAS = ['Biomédicos', 'Cómputo', 'Mobiliario', 'Electrodomésticos', 'Periféricos']

export interface UbicacionFicticia {
  id: string
  nombre: string
  tipo: 'sede' | 'sala' | 'box'
  padre?: string
}

export const UBICACIONES: UbicacionFicticia[] = [
  { id: 'sede', nombre: 'Sede Principal', tipo: 'sede' },
  { id: 'recepcion', nombre: 'Recepción', tipo: 'sala', padre: 'sede' },
  { id: 'c1', nombre: 'Consultorio 1', tipo: 'sala', padre: 'sede' },
  { id: 'c1b1', nombre: 'Box 1', tipo: 'box', padre: 'c1' },
  { id: 'c1b2', nombre: 'Box 2', tipo: 'box', padre: 'c1' },
  { id: 'c2', nombre: 'Consultorio 2', tipo: 'sala', padre: 'sede' },
  { id: 'esterilizacion', nombre: 'Esterilización', tipo: 'sala', padre: 'sede' },
  { id: 'rayosx', nombre: 'Rayos X', tipo: 'sala', padre: 'sede' },
  { id: 'administracion', nombre: 'Administración', tipo: 'sala', padre: 'sede' },
  { id: 'bodega', nombre: 'Bodega', tipo: 'sala', padre: 'sede' },
]

/** Ruta legible "Consultorio 1 › Box 2" (sin la sede, que es una sola). */
export function rutaUbicacion(id: string): string {
  const u = UBICACIONES.find((x) => x.id === id)
  if (!u) return ''
  if (u.tipo === 'box' && u.padre) return `${rutaUbicacion(u.padre)} › ${u.nombre}`
  return u.nombre
}

export const ACTIVOS: ActivoFicticio[] = [
  { codigo: '000102', nombre: 'Unidad odontológica', categoria: 'Biomédicos', ubicacion: 'Consultorio 1 › Box 1', estado: 'activo', conteo: 'verificado', precio: '38500000.00' },
  { codigo: '000103', nombre: 'Unidad odontológica', categoria: 'Biomédicos', ubicacion: 'Consultorio 2', estado: 'activo', conteo: 'pendiente', precio: '36900000.00' },
  { codigo: '000123', nombre: 'Autoclave clase B 18 L', categoria: 'Biomédicos', ubicacion: 'Esterilización', estado: 'activo', conteo: 'verificado', precio: '14200000.00' },
  { codigo: '000131', nombre: 'Compresor libre de aceite', categoria: 'Biomédicos', ubicacion: 'Bodega', estado: 'en_reparacion', conteo: 'pendiente', precio: '6900000.00' },
  { codigo: '000144', nombre: 'Lámpara de fotocurado LED', categoria: 'Biomédicos', ubicacion: 'Consultorio 1 › Box 2', estado: 'activo', conteo: 'verificado', precio: '1250000.00' },
  { codigo: '000150', nombre: 'Rayos X intraoral', categoria: 'Biomédicos', ubicacion: 'Rayos X', estado: 'activo', conteo: 'verificado', precio: '21800000.00' },
  { codigo: '000188', nombre: 'CPU de escritorio', categoria: 'Cómputo', ubicacion: 'Recepción', estado: 'activo', conteo: 'verificado', precio: '2180000.00' },
  { codigo: '000210', nombre: 'Monitor 24″', categoria: 'Periféricos', ubicacion: 'Recepción', estado: 'activo', conteo: 'otra_ubicacion', precio: '690000.00' },
  { codigo: '000215', nombre: 'Impresora multifuncional', categoria: 'Periféricos', ubicacion: 'Administración', estado: 'activo', conteo: 'verificado', precio: '1390000.00' },
  { codigo: '000301', nombre: 'Escritorio en L', categoria: 'Mobiliario', ubicacion: 'Administración', estado: 'activo', conteo: 'pendiente', precio: '980000.00' },
  { codigo: '000312', nombre: 'Nevera minibar', categoria: 'Electrodomésticos', ubicacion: 'Esterilización', estado: 'activo', conteo: 'pendiente', precio: '1642000.00' },
  { codigo: '000457', nombre: 'Silla ergonómica', categoria: 'Mobiliario', ubicacion: 'Consultorio 1 › Box 2', estado: 'activo', conteo: 'pendiente', precio: '389900.00', nuevoHoy: true },
]

export const TOTAL_ACTIVOS = 219

// Inicio (CU-DSH-01): cifras del servidor, en tiempo real.
export const RESUMEN = {
  activosHoy: 219,
  enReparacion: 2,
  valorActual: '286450300.00',
  consultadoA: '10:42',
  conteoAbierto: {
    nombre: 'Conteo nov 2026',
    corte: '30/11/2026',
    verificados: 132,
    total: 219,
    porcentaje: '60,3',
    pendientes: 87,
    pendientesPorUbicacion: [
      { ubicacion: 'Bodega', pendientes: 58, verificados: 0, total: 58 },
      { ubicacion: 'Administración', pendientes: 16, verificados: 13, total: 29 },
      { ubicacion: 'Consultorio 2', pendientes: 6, verificados: 30, total: 36 },
      { ubicacion: 'Rayos X', pendientes: 4, verificados: 5, total: 9 },
      { ubicacion: 'Consultorio 1', pendientes: 3, verificados: 38, total: 41 },
    ],
  },
  discrepancias: 3,
  danados: { total: 4, enReparacion: 2, danadosEnSesion: 2 },
}

export interface FilaDesglose {
  nombre: string
  encontrado: string
  encontradoU: number
  noEncontrado: string
  noEncontradoU: number
  total: string
  totalU: number
}

export interface NoEncontradoFicticio {
  codigo: string
  nombre: string
  categoria: string
  ubicacion: string
  precio: string
  enReparacion: boolean
}

// Último informe cerrado (CU-INF-01): congelado al cierre (R4, R9, R9a).
export const ULTIMO_INFORME = {
  sesion: 'Conteo may 2026',
  corte: '15/05/2026',
  cerradaEn: '16/05/2026 · 17:40',
  cerradaPor: 'Ana Torres',
  encontrado: { valor: '262118400.00', unidades: 198 },
  noEncontrado: { valor: '14731900.00', unidades: 9, enReparacion: 1 },
  total: { valor: '276850300.00', unidades: 207 },
  porcentajeEncontrado: '95,7',
  porCategoria: [
    { nombre: 'Biomédicos', encontrado: '156300000.00', encontradoU: 38, noEncontrado: '4900000.00', noEncontradoU: 1, total: '161200000.00', totalU: 39 },
    { nombre: 'Cómputo', encontrado: '39860500.00', encontradoU: 33, noEncontrado: '5447000.00', noEncontradoU: 3, total: '45307500.00', totalU: 36 },
    { nombre: 'Mobiliario', encontrado: '36104900.00', encontradoU: 88, noEncontrado: '1912900.00', noEncontradoU: 3, total: '38017800.00', totalU: 91 },
    { nombre: 'Electrodomésticos', encontrado: '17080000.00', encontradoU: 12, noEncontrado: '1642000.00', noEncontradoU: 1, total: '18722000.00', totalU: 13 },
    { nombre: 'Periféricos', encontrado: '12773000.00', encontradoU: 27, noEncontrado: '830000.00', noEncontradoU: 1, total: '13603000.00', totalU: 28 },
  ] satisfies FilaDesglose[],
  porUbicacion: [
    { nombre: 'Recepción', encontrado: '16100000.00', encontradoU: 20, noEncontrado: '1630000.00', noEncontradoU: 2, total: '17730000.00', totalU: 22 },
    { nombre: 'Consultorio 1', encontrado: '9850000.00', encontradoU: 7, noEncontrado: '0.00', noEncontradoU: 0, total: '9850000.00', totalU: 7 },
    { nombre: 'Consultorio 1 › Box 1', encontrado: '37210000.00', encontradoU: 17, noEncontrado: '650000.00', noEncontradoU: 1, total: '37860000.00', totalU: 18 },
    { nombre: 'Consultorio 1 › Box 2', encontrado: '33400000.00', encontradoU: 14, noEncontrado: '0.00', noEncontradoU: 0, total: '33400000.00', totalU: 14 },
    { nombre: 'Consultorio 2', encontrado: '63835500.00', encontradoU: 34, noEncontrado: '4900000.00', noEncontradoU: 1, total: '68735500.00', totalU: 35 },
    { nombre: 'Esterilización', encontrado: '33060000.00', encontradoU: 20, noEncontrado: '1642000.00', noEncontradoU: 1, total: '34702000.00', totalU: 21 },
    { nombre: 'Rayos X', encontrado: '41300000.00', encontradoU: 9, noEncontrado: '0.00', noEncontradoU: 0, total: '41300000.00', totalU: 9 },
    { nombre: 'Administración', encontrado: '14560000.00', encontradoU: 24, noEncontrado: '5520000.00', noEncontradoU: 3, total: '20080000.00', totalU: 27 },
    { nombre: 'Bodega', encontrado: '12802900.00', encontradoU: 53, noEncontrado: '389900.00', noEncontradoU: 1, total: '13192800.00', totalU: 54 },
  ] satisfies FilaDesglose[],
  noEncontrados: [
    { codigo: '000118', nombre: 'Ultrasonido de profilaxis', categoria: 'Biomédicos', ubicacion: 'Consultorio 2', precio: '4900000.00', enReparacion: true },
    { codigo: '000271', nombre: 'Portátil', categoria: 'Cómputo', ubicacion: 'Administración', precio: '2467000.00', enReparacion: false },
    { codigo: '000192', nombre: 'CPU de escritorio', categoria: 'Cómputo', ubicacion: 'Administración', precio: '2180000.00', enReparacion: false },
    { codigo: '000330', nombre: 'Nevera minibar', categoria: 'Electrodomésticos', ubicacion: 'Esterilización', precio: '1642000.00', enReparacion: false },
    { codigo: '000405', nombre: 'Archivador metálico 4 gavetas', categoria: 'Mobiliario', ubicacion: 'Administración', precio: '873000.00', enReparacion: false },
    { codigo: '000236', nombre: 'Impresora térmica de etiquetas', categoria: 'Periféricos', ubicacion: 'Recepción', precio: '830000.00', enReparacion: false },
    { codigo: '000277', nombre: 'Tableta', categoria: 'Cómputo', ubicacion: 'Recepción', precio: '800000.00', enReparacion: false },
    { codigo: '000412', nombre: 'Taburete odontológico', categoria: 'Mobiliario', ubicacion: 'Consultorio 1 › Box 1', precio: '650000.00', enReparacion: false },
    { codigo: '000398', nombre: 'Silla ergonómica', categoria: 'Mobiliario', ubicacion: 'Bodega', precio: '389900.00', enReparacion: false },
  ] satisfies NoEncontradoFicticio[],
}

export interface EventoFicticio {
  hora: string
  usuario: string
  tipo: 'verificado' | 'creado' | 'otra_ubicacion' | 'estado_cambiado' | 'precio_cambiado'
  activo: string
  codigo: string
  detalle: string
  /** true si el detalle contiene un precio: el contador no recibe el evento (P13). */
  conPrecio?: boolean
}

export const ACTIVIDAD: EventoFicticio[] = [
  { hora: '13/11 · 10:42', usuario: 'Luis Pérez', tipo: 'verificado', activo: 'Autoclave clase B 18 L', codigo: '000123', detalle: 'Esterilización · estado ok' },
  { hora: '13/11 · 10:40', usuario: 'Luis Pérez', tipo: 'creado', activo: 'Silla ergonómica', codigo: '000457', detalle: 'Consultorio 1 › Box 2' },
  { hora: '13/11 · 10:31', usuario: 'Sofía Rojas', tipo: 'verificado', activo: 'Unidad odontológica', codigo: '000102', detalle: 'Consultorio 1 › Box 1 · estado ok' },
  { hora: '13/11 · 10:18', usuario: 'Sofía Rojas', tipo: 'otra_ubicacion', activo: 'Monitor 24″', codigo: '000210', detalle: 'Esperada Recepción · encontrada Administración' },
  { hora: '13/11 · 09:55', usuario: 'Ana Torres', tipo: 'estado_cambiado', activo: 'Compresor libre de aceite', codigo: '000131', detalle: 'Activo → En reparación' },
  { hora: '13/11 · 09:15', usuario: 'Ana Torres', tipo: 'precio_cambiado', activo: 'Lámpara de fotocurado LED', codigo: '000144', detalle: '$ 1.180.000,00 → $ 1.250.000,00', conPrecio: true },
]
