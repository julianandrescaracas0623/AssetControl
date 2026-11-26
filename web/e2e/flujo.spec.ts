import { devices, expect, test } from '@playwright/test'

import { api, crearCuenta, texto, tokenDelTenant } from './ayuda.ts'

// Flujo real de punta a punta (spec 010c, T3; R3), con la API y la base de e2e:
// admin y contador en navegadores separados, conteo, cierre, informe, exportar e Inicio.
// Datos ficticios; nunca datos de la clínica.

test.describe.configure({ mode: 'serial' })

// PNG de 8x8 px de un solo color, generado para la prueba.
const FOTO = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEklEQVR4nGP4z8CAFWEXHbQSACj/P8Fu7N9hAAAAAElFTkSuQmCC',
  'base64',
)

test('un conteo completo: invitar, verificar en el teléfono, cerrar, informe, exportar e Inicio', async ({ browser }) => {
  const admin = await (await browser.newContext()).newPage()
  const errores: string[] = []
  admin.on('pageerror', (e) => errores.push(e.message))

  await test.step('el primer admin crea su cuenta con la invitación', async () => {
    await crearCuenta(admin, `/invitacion#${tokenDelTenant()}`, 'Ana E2E', 'Clave-E2E-Admin-2026')
    await expect(admin.getByRole('heading', { level: 1, name: 'Resumen' })).toBeVisible()
  })

  const llamar = api(admin)
  const sede = (await llamar<{ ubicacion: { id: string } }>('POST', '/ubicaciones', { nombre: 'Sede E2E', tipo: 'sede' })).ubicacion.id
  const sala = (await llamar<{ ubicacion: { id: string } }>('POST', '/ubicaciones', { nombre: 'Consultorios', tipo: 'sala', padre_id: sede })).ubicacion.id
  const box = (await llamar<{ ubicacion: { id: string } }>('POST', '/ubicaciones', { nombre: 'Box 1', tipo: 'box', padre_id: sala })).ubicacion.id
  const categorias = (await llamar<{ categorias: { id: string; nombre: string }[] }>('POST', '/categorias/sugeridas')).categorias
  const bio = categorias.find((c) => c.nombre === 'Biomédicos')!.id
  const alta = (codigo: string, nombre: string, precio: string) =>
    llamar<{ activo: { id: string } }>('POST', '/activos', { id: crypto.randomUUID(), codigo, nombre, precio_compra: precio, categoria_id: bio, ubicacion_id: box })
  await alta('E2E-0001', 'Autoclave E2E', '1390000.50')
  await alta('E2E-0002', 'Lámpara E2E', '389900.00')
  const compresor = (await alta('E2E-0003', 'Compresor E2E', '2000000.00')).activo
  expect((await llamar('POST', `/activos/${compresor.id}/estado`, { estado: 'en_reparacion' }, 1)).status).toBe(200)
  const sesion = (await llamar<{ sesion: { id: string } }>('POST', '/sesiones', { nombre: 'Conteo E2E', fecha_corte: '2026-11-30' })).sesion

  let enlace = ''
  await test.step('el admin invita a un contador', async () => {
    await admin.goto('/app/usuarios')
    await admin.getByLabel('Correo de la persona').fill('luis@e2e.ejemplo.test')
    await admin.getByRole('button', { name: 'Crear invitación' }).click()
    enlace = await admin.getByLabel('Enlace de invitación').inputValue()
    expect(enlace).toContain('/invitacion#')
  })

  const telefono = await (await browser.newContext({ ...devices['Pixel 7'] })).newPage()
  telefono.on('pageerror', (e) => errores.push(e.message))
  await test.step('el contador entra en el teléfono y verifica un activo escribiendo el código', async () => {
    await crearCuenta(telefono, new URL(enlace).pathname + new URL(enlace).hash, 'Luis E2E', 'Clave-E2E-Contador-2026')
    await expect(telefono.getByRole('heading', { level: 1, name: 'Conteo E2E' })).toBeVisible()
    await telefono.getByRole('combobox', { name: 'Estás contando en' }).click()
    await telefono.getByRole('option', { name: 'Consultorios › Box 1', exact: true }).click()
    await telefono.goto('/contar/escribir')
    await telefono.getByLabel('Código del sticker').fill('e2e-0001')
    await telefono.getByRole('button', { name: 'Buscar', exact: true }).click()
    await expect(telefono.getByRole('heading', { level: 1, name: 'Autoclave E2E' })).toBeVisible()
    await telefono.getByRole('button', { name: 'Confirmar' }).click()
    await expect(telefono.getByRole('heading', { level: 1, name: 'Verificado' })).toBeVisible()
    // El contador nunca ve pesos (P13).
    await expect(telefono.locator('body')).not.toContainText('$')
  })

  await test.step('el contador agrega una foto a la verificación (spec 012)', async () => {
    await telefono.getByRole('button', { name: 'Agregar foto (opcional)' }).click()
    await telefono.getByTestId('entrada-foto-verificacion').setInputFiles({ name: 'daño.png', mimeType: 'image/png', buffer: FOTO })
    await expect(telefono.getByText('Foto guardada.')).toBeVisible()
  })

  await test.step('el admin completa los datos y el logo de la empresa (spec 013)', async () => {
    await admin.goto('/app/empresa')
    await admin.getByRole('textbox', { name: /Nombre o razón social/ }).fill('Clínica E2E S.A.S.')
    await admin.getByRole('textbox', { name: /Dirección/ }).fill('Calle 1 # 2-3, Cartago')
    await admin.getByRole('textbox', { name: /NIT/ }).fill('900123456-8')
    await admin.getByRole('button', { name: 'Guardar datos' }).click()
    await expect(admin.getByRole('textbox', { name: /NIT/ })).toHaveValue('900.123.456-8')
    await admin.getByTestId('entrada-logo').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: FOTO })
    await expect(admin.getByRole('img', { name: 'Logo de Clínica E2E S.A.S.' })).toBeVisible()
  })

  await test.step('el admin cierra con el aviso y llega al informe', async () => {
    await admin.goto(`/app/sesiones/${sesion.id}`)
    await admin.getByRole('button', { name: 'Cerrar sesión' }).click()
    const dialogo = admin.getByRole('dialog', { name: '¿Cerrar «Conteo E2E»?' })
    await expect(dialogo.getByText('2 activos sin verificar quedarán como no encontrados.')).toBeVisible()
    await dialogo.getByRole('button', { name: 'Cerrar y ver informe' }).click()
    await expect(admin.getByRole('heading', { level: 1, name: 'Informe · Conteo E2E' })).toBeVisible()
    const cifras = texto(await admin.getByRole('region', { name: /Informe congelado/ }).textContent())
    expect(cifras).toContain('Encontrado$ 1.390.000,50')
    expect(cifras).toContain('No encontrado$ 2.389.900,00')
    expect(cifras).toContain('Total registrado$ 3.779.900,50')
    await expect(admin.getByText('Clínica E2E S.A.S.', { exact: true })).toBeVisible()
    const informe = await llamar<{ empresa: { nombre: string; nit: string; logo: object | null; vigente: boolean }; detalle_disponible: boolean }>(
      'GET',
      `/sesiones/${sesion.id}/informe`,
    )
    expect(informe.empresa).toMatchObject({ nombre: 'Clínica E2E S.A.S.', nit: '900.123.456-8', vigente: false })
    expect(informe.empresa.logo).not.toBeNull()
    expect(informe.detalle_disponible).toBe(true)
  })

  await test.step('exportar Excel y PDF descarga los archivos del servidor', async () => {
    for (const [boton, extension] of [['Exportar Excel', 'xlsx'], ['Exportar PDF', 'pdf']] as const) {
      const [descarga] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('button', { name: boton }).click()])
      expect(descarga.suggestedFilename()).toBe(`informe-conteo-e2e-corte-2026-11-30.${extension}`)
    }
  })

  await test.step('el admin exporta la lista filtrada y abre la ficha con doble clic (spec 015, T4)', async () => {
    await admin.goto('/app/activos')
    await admin.getByRole('searchbox', { name: 'Buscar activos' }).fill('autoclave')
    await expect(admin.getByRole('row')).toHaveCount(2)
    const [descarga] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('button', { name: 'Exportar' }).click()])
    expect(descarga.suggestedFilename()).toMatch(/^activos-\d{8}\.xlsx$/)
    await expect(admin.getByText(/^Se descargó «activos-\d{8}\.xlsx»$/)).toBeVisible()
    await admin.getByRole('row', { name: /E2E-0001/ }).getByRole('cell', { name: 'Biomédicos' }).dblclick()
    await expect(admin.getByRole('heading', { level: 1, name: 'Autoclave E2E' })).toBeVisible()
    // El contador no exporta (403 del servidor, no solo un botón escondido).
    expect((await api(telefono)('GET', '/activos/exportar')).status).toBe(403)
  })

  await test.step('el Inicio del admin muestra el último informe y el valor actual por separado', async () => {
    await admin.goto('/app')
    await expect(admin.getByRole('link', { name: /Activos hoy/ })).toContainText('3')
    const informe = admin.getByRole('region', { name: /Informe congelado/ })
    await expect(informe).toContainText('3.779.900,50')
    await expect(admin.getByRole('figure', { name: 'Evolución entre conteos' })).toContainText('Conteo E2E')
  })

  await test.step('el Inicio del contador no tiene ningún precio', async () => {
    await telefono.goto('/contar')
    await expect(telefono.getByRole('region', { name: 'Activos hoy' })).toContainText('3')
    await expect(telefono.getByRole('region', { name: 'Actividad reciente' })).toBeVisible()
    await expect(telefono.locator('body')).not.toContainText('$')
    await expect(telefono.locator('body')).not.toContainText('Precio cambiado')
  })

  expect(errores).toEqual([])
})
