import { expect, type Page, test } from '@playwright/test'

import { api, crearCuenta, desarrolladorE2E } from './ayuda.ts'

// Consola de plataforma de punta a punta (spec 017, T9; A7, A9, A14, A19; CU-01, CU-03 a
// CU-06, CU-10; C1: A21–A26, CU-12, CU-13; C1b: A27–A29, CU-14), con la API y la base de e2e reales y
// PLATAFORMA_HABILITADA=true: el desarrollador (creado con la CLI de T1 en e2e/base.py) entra,
// recarga (la cookie de plataforma pasa por el proxy de Vite), crea una empresa con su primer
// admin y su logo en un solo formulario (C1c), la desactiva y la reactiva; el admin entra con la contraseña inicial, la cambia en la
// pantalla obligatoria y llega a /admin. Datos ficticios; nunca datos de la clínica.

test.describe.configure({ mode: 'serial' })

// D21: este archivo escribe contraseñas (la inicial del admin, la del contador, la del
// desarrollador). La traza y el vídeo guardan lo escrito en los campos y la CI sube
// test-results/ si falla: aquí no se graban. flujo.spec.ts sigue con la configuración global.
test.use({ trace: 'off', video: 'off' })

// PNG de 8x8 px de un solo color, generado para la prueba.
const LOGO = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEklEQVR4nGP4z8CAFWEXHbQSACj/P8Fu7N9hAAAAAElFTkSuQmCC',
  'base64',
)
// C1: otro PNG de 8x8 px (rojo) para reemplazar el logo.
const LOGO_NUEVO = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGM4oaGBFTEMLQkAgl1GAWqNFmsAAAAASUVORK5CYII=', 'base64')

const EMPRESA = 'Clínica Plataforma E2E'
const ADMIN = 'admin.plataforma@e2e.ejemplo.test'
const INICIAL = 'Inicial-Plataforma-2026'
const NUEVA = 'Nueva-Del-Admin-2026'

const fila = (page: Page) => page.getByRole('row').filter({ hasText: EMPRESA })
// Spec 017, T10.
const CONTADOR = 'luis.plataforma@e2e.ejemplo.test'
const CLAVE_CONTADOR = 'Clave-Contador-Plataforma-2026'

async function entrarConsola(page: Page) {
  const { email, password } = desarrolladorE2E()
  await page.goto('/plataforma')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Empresas' })).toBeVisible()
}

async function entrarClinica(page: Page, clave: string) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(ADMIN)
  await page.getByLabel('Contraseña', { exact: true }).fill(clave)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
}

test('consola: crear empresa con admin y logo, desactivar y reactivar; el admin cambia su contraseña y entra', async ({ browser }) => {
  const dev = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  const errores: string[] = []
  dev.on('pageerror', (e) => errores.push(e.message))
  const enUrl: string[] = []
  // La contraseña inicial solo viaja en el cuerpo del POST, nunca en una URL.
  dev.on('request', (r) => {
    if (r.url().includes(INICIAL)) enUrl.push(r.url())
  })

  await test.step('el desarrollador entra a la consola', async () => {
    const { email, password } = desarrolladorE2E()
    await dev.goto('/plataforma')
    await expect(dev.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
    await dev.getByLabel('Correo').fill(email)
    await dev.getByLabel('Contraseña', { exact: true }).fill(password)
    await dev.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Empresas' })).toBeVisible()
    await expect(dev.getByRole('link', { name: 'Empresas' })).toHaveAttribute('aria-current', 'page')
  })

  await test.step('al recargar sigue dentro: la cookie de plataforma renueva por el proxy', async () => {
    await dev.reload()
    await expect(dev.getByRole('heading', { level: 1, name: 'Empresas' })).toBeVisible()
    const plat = (await dev.context().cookies()).find((c) => c.name.includes('plat-refresh'))
    expect(plat?.httpOnly).toBe(true)
    expect(plat?.path).toBe('/api/plataforma/auth')
  })

  await test.step('formulario único: ficha, logo y primer admin (C1c; R46)', async () => {
    await dev.getByRole('link', { name: 'Nueva empresa' }).first().click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Nueva empresa' })).toBeVisible()
    // C1c: un solo formulario, sin pasos ni barra de progreso.
    await expect(dev.getByText(/Paso \d de 2/)).toHaveCount(0)
    await expect(dev.getByRole('progressbar')).toHaveCount(0)
    await dev.getByRole('textbox', { name: /^Nombre o razón social/ }).fill(EMPRESA)
    await dev.getByRole('textbox', { name: /^Dirección/ }).fill('Carrera 4 # 12-30, Cartago')
    await dev.getByRole('textbox', { name: /^NIT/ }).fill('900123456-8')
    await dev.getByTestId('entrada-logo-alta').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: LOGO })
    await expect(dev.getByRole('img', { name: 'Vista previa del logo' })).toBeVisible()
    await dev.getByRole('textbox', { name: /^Nombre\*?$/ }).fill('Ana Plataforma')
    await dev.getByRole('textbox', { name: /^Correo\*?$/ }).fill(ADMIN)
    await dev.locator('#alta-admin-password').fill(INICIAL)
    await dev.locator('#alta-admin-password_confirmacion').fill(INICIAL)
    await dev.getByRole('button', { name: 'Crear empresa' }).click()
    // La web crea la empresa y sube el logo en una segunda llamada, sin otro paso.
    await expect(dev.getByRole('heading', { name: 'Empresa lista' })).toBeVisible()
    await expect(dev.getByText(/y con su logo/)).toBeVisible()
    // D17: `content()` no incluye el `value` de los campos, así que además se leen los valores
    // de todos los campos, el almacenamiento, la URL y el historial.
    expect(await dev.content()).not.toContain(INICIAL)
    await expect(dev.locator('#alta-admin-password, #alta-admin-password_confirmacion')).toHaveCount(0)
    const valores = await Promise.all((await dev.locator('input, textarea').all()).map((c) => c.inputValue()))
    expect(valores.join('\n')).not.toContain(INICIAL)
    // Expresión en texto: el tsconfig de e2e no incluye los tipos del DOM.
    const almacenado = String(
      await dev.evaluate('JSON.stringify([{ ...localStorage }, { ...sessionStorage }, location.href, history.state ?? null])'),
    )
    expect(almacenado).not.toContain(INICIAL)
    await dev.getByRole('link', { name: 'Volver a empresas' }).click()
    await expect(fila(dev)).toContainText('Activa')
    await expect(fila(dev)).toContainText('Sí')
  })

  const admin = await (await browser.newContext()).newPage()
  admin.on('pageerror', (e) => errores.push(e.message))

  await test.step('desactivada, su admin no puede entrar (A9)', async () => {
    await fila(dev).getByRole('button', { name: `Acciones de ${EMPRESA}` }).click()
    await dev.getByRole('menuitem', { name: 'Desactivar' }).click()
    const dialogo = dev.getByRole('alertdialog')
    await expect(dialogo).toContainText(`Los usuarios de ${EMPRESA} no podrán entrar. No se borra nada.`)
    await dialogo.getByRole('button', { name: 'Sí, desactivar' }).click()
    await expect(fila(dev)).toContainText('Desactivada')

    await entrarClinica(admin, INICIAL)
    await expect(admin.getByText(/incorrectos/)).toBeVisible()
  })

  await test.step('reactivada, el admin entra y debe cambiar la contraseña (CU-10)', async () => {
    await fila(dev).getByRole('button', { name: `Acciones de ${EMPRESA}` }).click()
    await dev.getByRole('menuitem', { name: 'Reactivar' }).click()
    await dev.getByRole('alertdialog').getByRole('button', { name: 'Sí, reactivar' }).click()
    await expect(fila(dev)).toContainText('Activa')
    await expect(fila(dev)).not.toContainText('Desactivada')

    await entrarClinica(admin, INICIAL)
    await expect(admin.getByRole('heading', { level: 1, name: 'Cambia tu contraseña' })).toBeVisible()
    await expect(admin).toHaveURL(/\/cambiar-contrasena$/)
    await admin.goto('/admin/activos')
    await expect(admin.getByRole('heading', { level: 1, name: 'Cambia tu contraseña' })).toBeVisible()
  })

  await test.step('cambia la contraseña y entra a /admin (A7)', async () => {
    await admin.getByLabel('Contraseña actual', { exact: true }).fill(INICIAL)
    await admin.getByLabel('Contraseña nueva', { exact: true }).fill(NUEVA)
    await admin.getByLabel('Confirma la contraseña nueva', { exact: true }).fill(NUEVA)
    await admin.getByRole('button', { name: 'Guardar contraseña' }).click()
    await expect(admin).toHaveURL(/\/admin(\/activos)?$/)
    await admin.goto('/admin')
    await expect(admin.getByRole('heading', { level: 1, name: 'Resumen' })).toBeVisible()
  })

  await test.step('el admin ve el logo que subió el desarrollador (A19)', async () => {
    await admin.goto('/admin/empresa')
    await expect(admin.getByRole('img', { name: `Logo de ${EMPRESA}` })).toBeVisible()
  })

  await test.step('la consola sigue sin datos de negocio', async () => {
    await dev.reload()
    await expect(fila(dev)).toContainText('Activa')
    await expect(dev.locator('body')).not.toContainText('$')
  })

  expect(enUrl).toEqual([])
  expect(errores).toEqual([])
})

// Spec 017, T10 (A17, A18; CU-05, CU-07, CU-08): con la empresa del caso anterior, el admin
// invita a un contador; el desarrollador abre sus usuarios desde Empresas, no puede
// desactivar al último admin, desactiva al contador (que pierde su sesión y no vuelve a
// entrar) y Actividad muestra la desactivación y los demás pasos de la empresa.
test('consola: usuarios de una empresa (último admin, desactivar con efecto) y su actividad', async ({ browser }) => {
  const errores: string[] = []
  const admin = await (await browser.newContext()).newPage()
  admin.on('pageerror', (e) => errores.push(e.message))
  const contador = await (await browser.newContext({ viewport: { width: 375, height: 812 } })).newPage()
  contador.on('pageerror', (e) => errores.push(e.message))
  const dev = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  dev.on('pageerror', (e) => errores.push(e.message))

  await test.step('el admin invita a un contador y este crea su cuenta', async () => {
    await entrarClinica(admin, NUEVA)
    await expect(admin).toHaveURL(/\/admin/)
    await admin.goto('/admin/usuarios')
    await admin.getByLabel('Correo de la persona').fill(CONTADOR)
    await admin.getByRole('button', { name: 'Crear invitación' }).click()
    const enlace = new URL(await admin.getByLabel('Enlace de invitación').inputValue())
    await crearCuenta(contador, enlace.pathname + enlace.hash, 'Luis Plataforma', CLAVE_CONTADOR)
    await expect(contador).toHaveURL(/\/contar/)
  })

  await test.step('desde Empresas, «Ver usuarios» abre los usuarios de esa empresa (CU-05)', async () => {
    await entrarConsola(dev)
    await fila(dev).getByRole('button', { name: `Acciones de ${EMPRESA}` }).click()
    await dev.getByRole('menuitem', { name: 'Ver usuarios' }).click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Usuarios' })).toBeVisible()
    await expect(dev).toHaveURL(/\/plataforma\/usuarios\?empresa=[0-9a-f-]{36}$/)
    const tabla = dev.getByRole('table', { name: `Usuarios de ${EMPRESA}` })
    const ana = tabla.getByRole('row').filter({ hasText: 'Ana Plataforma' })
    await expect(ana).toContainText('Admin')
    // Ya cambió su contraseña en el caso anterior: sin marca pendiente.
    await expect(ana).not.toContainText('Cambio de contraseña pendiente')
    const luis = tabla.getByRole('row').filter({ hasText: 'Luis Plataforma' })
    await expect(luis).toContainText('Contador')
    await expect(luis).toContainText('Activo')
  })

  await test.step('no se puede desactivar al último admin activo (409 ultimo_admin)', async () => {
    await dev.getByRole('button', { name: 'Desactivar a Ana Plataforma' }).click()
    await dev.getByRole('alertdialog').getByRole('button', { name: 'Sí, desactivar' }).click()
    await expect(dev.getByText('No se puede desactivar al último admin activo de la empresa')).toBeVisible()
    await expect(dev.getByRole('row').filter({ hasText: 'Ana Plataforma' })).toContainText('Activo')
  })

  await test.step('desactivado, el contador pierde su sesión y no vuelve a entrar (A17)', async () => {
    await dev.getByRole('button', { name: 'Desactivar a Luis Plataforma' }).click()
    const dialogo = dev.getByRole('alertdialog')
    await expect(dialogo).toContainText(`Luis Plataforma no podrá entrar a ${EMPRESA}.`)
    await expect(dialogo).toContainText('Si tiene una sesión abierta, se cierra en su siguiente acción.')
    await dialogo.getByRole('button', { name: 'Sí, desactivar' }).click()
    await expect(dev.getByRole('row').filter({ hasText: 'Luis Plataforma' })).toContainText('Desactivado')

    await contador.reload()
    await expect(contador.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
    await contador.getByLabel('Correo').fill(CONTADOR)
    await contador.getByLabel('Contraseña', { exact: true }).fill(CLAVE_CONTADOR)
    await contador.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(contador.getByText(/incorrectos/)).toBeVisible()
  })

  await test.step('Actividad muestra lo hecho con la empresa, con filtros (A18)', async () => {
    await dev.getByRole('link', { name: 'Actividad' }).click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Actividad' })).toBeVisible()
    await dev.getByRole('button', { name: 'Empresa', exact: true }).click()
    await dev.getByRole('radio', { name: EMPRESA }).click()
    await dev.keyboard.press('Escape')
    const tabla = dev.getByRole('table', { name: 'Actividad' })
    // De la más reciente a la más antigua; el intento rechazado (último admin) no se audita.
    await expect(tabla.getByRole('row').nth(1)).toContainText('Usuario desactivado')
    for (const accion of ['Empresa creada', 'Logo subido', 'Empresa desactivada', 'Empresa reactivada']) {
      await expect(tabla.getByRole('row').filter({ hasText: accion })).toHaveCount(1)
    }
    await dev.getByRole('button', { name: 'Acción', exact: true }).click()
    await dev.getByRole('radio', { name: 'Usuario desactivado' }).click()
    await dev.keyboard.press('Escape')
    await expect(tabla.getByRole('row')).toHaveCount(2)
    await expect(tabla).toContainText(EMPRESA)
    await expect(dev.locator('body')).not.toContainText(CONTADOR)
  })

  await test.step('reactivado, el contador vuelve a entrar', async () => {
    await dev.getByRole('link', { name: 'Usuarios' }).click()
    await dev.getByRole('combobox', { name: 'Empresa' }).click()
    await dev.getByRole('option', { name: EMPRESA }).click()
    await dev.getByRole('button', { name: 'Reactivar a Luis Plataforma' }).click()
    await dev.getByRole('alertdialog').getByRole('button', { name: 'Sí, reactivar' }).click()
    await expect(dev.getByRole('row').filter({ hasText: 'Luis Plataforma' })).toContainText('Activo')
    await contador.getByLabel('Contraseña', { exact: true }).fill(CLAVE_CONTADOR)
    await contador.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(contador).toHaveURL(/\/contar/)
  })

  expect(errores).toEqual([])
})

// Spec 017, C1 (T15; A21–A26; CU-12, CU-13): con la empresa de los casos anteriores, el
// desarrollador edita la ficha y reemplaza el logo (el admin ve los dos cambios en
// /admin/empresa), no puede quitarle el rol admin a la última admin, hace admin al contador
// (que pierde su sesión y al volver a entrar ya abre /admin) y Actividad registra las tres
// acciones nuevas. Depende de los dos casos anteriores (modo serial, D25).
test('consola: editar empresa y logo, cambiar el rol de un usuario y su actividad (C1)', async ({ browser }) => {
  const errores: string[] = []
  const admin = await (await browser.newContext()).newPage()
  admin.on('pageerror', (e) => errores.push(e.message))
  const contador = await (await browser.newContext({ viewport: { width: 375, height: 812 } })).newPage()
  contador.on('pageerror', (e) => errores.push(e.message))
  const dev = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  dev.on('pageerror', (e) => errores.push(e.message))
  const DIRECCION = 'Calle 10 # 5-20, Cartago'
  const logoDelAdmin = async () => (await api(admin)<{ empresa: { logo: { id: string } | null } }>('GET', '/empresa')).empresa.logo?.id ?? null

  let logoAntes: string | null = null
  await test.step('el admin y el contador entran', async () => {
    await entrarClinica(admin, NUEVA)
    await expect(admin).toHaveURL(/\/admin/)
    logoAntes = await logoDelAdmin()
    expect(logoAntes).not.toBeNull()
    await contador.goto('/login')
    await contador.getByLabel('Correo').fill(CONTADOR)
    await contador.getByLabel('Contraseña', { exact: true }).fill(CLAVE_CONTADOR)
    await contador.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(contador).toHaveURL(/\/contar/)
  })

  await test.step('Editar empresa: guarda la ficha (A21)', async () => {
    await entrarConsola(dev)
    await fila(dev).getByRole('button', { name: `Acciones de ${EMPRESA}` }).click()
    await dev.getByRole('menuitem', { name: 'Editar' }).click()
    const dialogo = dev.getByRole('dialog', { name: 'Editar empresa' })
    const direccion = dialogo.getByRole('textbox', { name: /^Dirección/ })
    await expect(direccion).toHaveValue('Carrera 4 # 12-30, Cartago')
    await expect(dialogo.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
    await direccion.fill(DIRECCION)
    await dialogo.getByRole('button', { name: 'Guardar cambios' }).click()
    await expect(dialogo).toHaveCount(0)
  })

  await test.step('Editar empresa: reemplaza el logo (A22), abierto con doble clic en la fila', async () => {
    // Celda «Creada» (fecha): no es un control de la fila.
    await fila(dev).getByRole('cell').nth(2).dblclick()
    const dialogo = dev.getByRole('dialog', { name: 'Editar empresa' })
    await expect(dialogo).toHaveAttribute('data-forma', 'centrado')
    await expect(dialogo.getByRole('textbox', { name: /^Dirección/ })).toHaveValue(DIRECCION)
    await expect(dialogo.getByText('Tiene logo', { exact: true })).toBeVisible()
    await dialogo.getByTestId('entrada-logo-editar').setInputFiles({ name: 'logo-nuevo.png', mimeType: 'image/png', buffer: LOGO_NUEVO })
    await expect(dialogo.getByRole('img', { name: 'Vista previa del logo' })).toBeVisible()
    await dialogo.getByRole('button', { name: 'Reemplazar logo' }).click()
    await expect(dev.getByText(`Logo de ${EMPRESA} reemplazado`)).toBeVisible()
    await dialogo.getByRole('button', { name: 'Cancelar' }).click()
    await expect(dialogo).toHaveCount(0)
  })

  await test.step('el admin ve la ficha nueva y otro logo en /admin/empresa', async () => {
    await admin.goto('/admin/empresa')
    await expect(admin.getByRole('textbox', { name: /^Dirección/ })).toHaveValue(DIRECCION)
    await expect(admin.getByRole('img', { name: `Logo de ${EMPRESA}` })).toBeVisible()
    const logoDespues = await logoDelAdmin()
    expect(logoDespues).not.toBeNull()
    expect(logoDespues).not.toBe(logoAntes)
  })

  await test.step('Editar usuario: no se le quita el rol admin a la última admin (409 ultimo_admin)', async () => {
    await dev.getByRole('link', { name: 'Usuarios' }).click()
    await dev.getByRole('combobox', { name: 'Empresa' }).click()
    await dev.getByRole('option', { name: EMPRESA }).click()
    await dev.getByRole('button', { name: 'Editar a Ana Plataforma' }).click()
    const dialogo = dev.getByRole('dialog', { name: 'Editar usuario' })
    const correo = dialogo.getByRole('textbox', { name: /^Correo/ })
    await expect(correo).toHaveValue(ADMIN)
    await expect(correo).toBeDisabled()
    await dialogo.getByRole('combobox', { name: /^Rol/ }).click()
    await dev.getByRole('option', { name: 'Contador' }).click()
    await dialogo.getByRole('button', { name: 'Guardar cambios' }).click()
    await dev.getByRole('alertdialog').getByRole('button', { name: 'Sí, cambiar el rol' }).click()
    await expect(dialogo.getByText('No se puede quitar el rol admin al último admin activo de la empresa')).toBeVisible()
    await dialogo.getByRole('button', { name: 'Cancelar' }).click()
    await expect(dialogo).toHaveCount(0)
    await expect(dev.getByRole('row').filter({ hasText: 'Ana Plataforma' })).toContainText('Admin')
  })

  await test.step('Editar usuario: hacer admin al contador cierra su sesión; al volver abre /admin (A25)', async () => {
    await dev.getByRole('button', { name: 'Editar a Luis Plataforma' }).click()
    const dialogo = dev.getByRole('dialog', { name: 'Editar usuario' })
    await dialogo.getByRole('combobox', { name: /^Rol/ }).click()
    await dev.getByRole('option', { name: 'Admin' }).click()
    await dialogo.getByRole('button', { name: 'Guardar cambios' }).click()
    const confirmar = dev.getByRole('alertdialog')
    await expect(confirmar).toContainText(`Luis Plataforma pasará a ser admin en ${EMPRESA}.`)
    await expect(confirmar).toContainText('Su sesión abierta se cerrará y tendrá los permisos de admin.')
    await confirmar.getByRole('button', { name: 'Sí, cambiar el rol' }).click()
    await expect(dialogo).toHaveCount(0)
    await expect(dev.getByRole('row').filter({ hasText: 'Luis Plataforma' })).toContainText('Admin')

    // Su refresh se revocó: al recargar vuelve a «Iniciar sesión».
    await contador.reload()
    await expect(contador.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
    await contador.getByLabel('Correo').fill(CONTADOR)
    await contador.getByLabel('Contraseña', { exact: true }).fill(CLAVE_CONTADOR)
    await contador.getByRole('button', { name: 'Entrar', exact: true }).click()
    // Vuelve a donde estaba (/contar); con el rol nuevo ya abre el panel de admin.
    await expect(contador).toHaveURL(/\/contar/)
    await contador.goto('/admin')
    await expect(contador.getByRole('heading', { level: 1, name: 'Resumen' })).toBeVisible()
  })

  await test.step('Actividad registra las tres acciones de C1 (A26)', async () => {
    await dev.getByRole('link', { name: 'Actividad' }).click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Actividad' })).toBeVisible()
    await dev.getByRole('button', { name: 'Empresa', exact: true }).click()
    await dev.getByRole('radio', { name: EMPRESA }).click()
    await dev.keyboard.press('Escape')
    const tabla = dev.getByRole('table', { name: 'Actividad' })
    // De la más reciente a la más antigua; el intento rechazado (última admin) no se audita.
    await expect(tabla.getByRole('row').nth(1)).toContainText('Usuario editado')
    for (const accion of ['Usuario editado', 'Logo reemplazado', 'Empresa editada', 'Logo subido']) {
      await expect(tabla.getByRole('row').filter({ hasText: accion })).toHaveCount(1)
    }
    await expect(dev.locator('body')).not.toContainText(CONTADOR)
    await expect(dev.locator('body')).not.toContainText(DIRECCION)
  })

  expect(errores).toEqual([])
})

// Spec 017, C1b (T16; R53–R60; A27–A29; CU-14): con la empresa de los casos anteriores, el
// desarrollador define una contraseña temporal para la admin. Su sesión abierta cae, la
// contraseña anterior deja de servir, con la temporal llega a «Cambia tu contraseña», la
// cambia y entra a /admin; la fila mostró «Cambio de contraseña pendiente» y Actividad registra
// «Contraseña temporal definida». La temporal solo viaja en el cuerpo del POST: nunca en una
// URL, en el DOM, en un campo tras responder ni en el almacenamiento. Datos sintéticos.
// Depende de los casos anteriores (modo serial, D25).
test('consola: contraseña temporal de un usuario; la persona la cambia al entrar (C1b)', async ({ browser }) => {
  const TEMPORAL = 'Temporal-Consola-E2E-2026'
  const FINAL = 'Final-De-Ana-E2E-2026'
  const errores: string[] = []
  const admin = await (await browser.newContext()).newPage()
  admin.on('pageerror', (e) => errores.push(e.message))
  const dev = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  dev.on('pageerror', (e) => errores.push(e.message))
  const enUrl: string[] = []
  dev.on('request', (r) => {
    if (r.url().includes(TEMPORAL)) enUrl.push(r.url())
  })
  const cuerpos: string[] = []
  dev.on('request', (r) => {
    if (r.url().endsWith('/contrasena') && r.method() === 'POST') cuerpos.push(r.postData() ?? '')
  })

  await test.step('la admin entra con su contraseña', async () => {
    await entrarClinica(admin, NUEVA)
    await expect(admin).toHaveURL(/\/admin/)
  })

  await test.step('el desarrollador define una temporal (confirmación con persona, empresa y efecto)', async () => {
    await entrarConsola(dev)
    await dev.getByRole('link', { name: 'Usuarios' }).click()
    await dev.getByRole('combobox', { name: 'Empresa' }).click()
    await dev.getByRole('option', { name: EMPRESA }).click()
    const ana = dev.getByRole('row').filter({ hasText: 'Ana Plataforma' })
    await expect(ana).not.toContainText('Cambio de contraseña pendiente')
    await dev.getByRole('button', { name: 'Restablecer la contraseña de Ana Plataforma' }).click()
    const dialogo = dev.getByRole('dialog', { name: 'Restablecer contraseña' })
    await expect(dialogo).toHaveAttribute('data-forma', 'centrado')
    const clave = dialogo.getByLabel(/^Contraseña temporal/)
    const confirmacion = dialogo.getByLabel(/^Confirmar contraseña/)
    await expect(clave).toHaveAttribute('autocomplete', 'new-password')
    await expect(clave).toHaveAttribute('type', 'password')
    await clave.fill(TEMPORAL)
    await confirmacion.fill(TEMPORAL)
    await dialogo.getByRole('button', { name: 'Definir contraseña' }).click()
    const confirmar = dev.getByRole('alertdialog')
    await expect(confirmar).toContainText(`Ana Plataforma en ${EMPRESA}`)
    await expect(confirmar).toContainText('Se cerrarán todas sus sesiones abiertas, también en otras empresas')
    await expect(confirmar).not.toContainText(TEMPORAL)
    await confirmar.getByRole('button', { name: 'Sí, definir la contraseña' }).click()
    await expect(dialogo).toHaveCount(0)
    await expect(dev.getByText('Contraseña temporal definida')).toBeVisible()
    await expect(ana).toContainText('Cambio de contraseña pendiente')

    // Un solo POST, con exactamente las dos claves.
    expect(cuerpos).toHaveLength(1)
    expect(Object.keys(JSON.parse(cuerpos[0]) as object).sort()).toEqual(['password', 'password_confirmacion'])
    expect(await dev.content()).not.toContain(TEMPORAL)
    const valores = await Promise.all((await dev.locator('input, textarea').all()).map((c) => c.inputValue()))
    expect(valores.join('\n')).not.toContain(TEMPORAL)
    const almacenado = String(
      await dev.evaluate('JSON.stringify([{ ...localStorage }, { ...sessionStorage }, location.href, history.state ?? null])'),
    )
    expect(almacenado).not.toContain(TEMPORAL)
  })

  await test.step('la sesión abierta de la admin cae y su contraseña anterior ya no sirve (A28)', async () => {
    await admin.reload()
    await expect(admin.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
    await entrarClinica(admin, NUEVA)
    await expect(admin.getByText(/incorrectos/)).toBeVisible()
  })

  await test.step('con la temporal llega a «Cambia tu contraseña», la cambia y entra a /admin', async () => {
    await entrarClinica(admin, TEMPORAL)
    await expect(admin.getByRole('heading', { level: 1, name: 'Cambia tu contraseña' })).toBeVisible()
    await admin.goto('/admin/activos')
    await expect(admin.getByRole('heading', { level: 1, name: 'Cambia tu contraseña' })).toBeVisible()
    await admin.getByLabel('Contraseña actual', { exact: true }).fill(TEMPORAL)
    await admin.getByLabel('Contraseña nueva', { exact: true }).fill(FINAL)
    await admin.getByLabel('Confirma la contraseña nueva', { exact: true }).fill(FINAL)
    await admin.getByRole('button', { name: 'Guardar contraseña' }).click()
    await expect(admin).toHaveURL(/\/admin(\/activos)?$/)
    await admin.goto('/admin')
    await expect(admin.getByRole('heading', { level: 1, name: 'Resumen' })).toBeVisible()
  })

  await test.step('la fila ya no tiene la marca y Actividad registra la acción (A29)', async () => {
    await dev.reload()
    await dev.getByRole('combobox', { name: 'Empresa' }).click()
    await dev.getByRole('option', { name: EMPRESA }).click()
    await expect(dev.getByRole('row').filter({ hasText: 'Ana Plataforma' })).not.toContainText('Cambio de contraseña pendiente')
    await dev.getByRole('link', { name: 'Actividad' }).click()
    await expect(dev.getByRole('heading', { level: 1, name: 'Actividad' })).toBeVisible()
    await dev.getByRole('button', { name: 'Empresa', exact: true }).click()
    await dev.getByRole('radio', { name: EMPRESA }).click()
    await dev.keyboard.press('Escape')
    const tabla = dev.getByRole('table', { name: 'Actividad' })
    await expect(tabla.getByRole('row').nth(1)).toContainText('Contraseña temporal definida')
    await expect(tabla.getByRole('row').filter({ hasText: 'Contraseña temporal definida' })).toHaveCount(1)
    await expect(dev.locator('body')).not.toContainText(ADMIN)
    expect(await dev.content()).not.toContain(TEMPORAL)
  })

  expect(enUrl).toEqual([])
  expect(errores).toEqual([])
})
