import { readFileSync } from 'node:fs'
import path from 'node:path'

import { expect, type Page } from '@playwright/test'

// Ayudas de las pruebas e2e (spec 010c, T3).

export function tokenDelTenant(): string {
  const archivo = path.join(import.meta.dirname, '.estado', 'tenant.json')
  return (JSON.parse(readFileSync(archivo, 'utf8')) as { token: string }).token
}

/** Llama a la API con la sesión de la página (renueva el token con la cookie, como la web). */
export function api(page: Page) {
  return async <T = Record<string, unknown>>(metodo: string, ruta: string, cuerpo?: unknown, version?: number): Promise<T & { status: number }> =>
    page.evaluate(
      async ([m, r, b, v]) => {
        const refresh = await fetch('/api/auth/refresh', { method: 'POST', headers: { 'X-AssetControl-CSRF': '1' } })
        const { access_token } = (await refresh.json()) as { access_token: string }
        const headers: Record<string, string> = { 'Content-Type': 'application/json', Authorization: `Bearer ${access_token}` }
        if (v) headers['If-Match'] = `"${v}"`
        const res = await fetch(`/api${r}`, { method: m, headers, body: b ? JSON.stringify(b) : undefined })
        return { status: res.status, ...((await res.json()) as object) }
      },
      [metodo, ruta, cuerpo, version] as const,
    ) as Promise<T & { status: number }>
}

export async function crearCuenta(page: Page, enlace: string, nombre: string, clave: string) {
  await page.goto(enlace)
  await expect(page.getByRole('heading', { level: 1, name: 'Crea tu cuenta' })).toBeVisible()
  await page.getByLabel('Nombre', { exact: true }).fill(nombre)
  await page.getByLabel('Contraseña', { exact: true }).fill(clave)
  await page.getByRole('button', { name: 'Crear cuenta y entrar' }).click()
}

/** "$ 1.390.000,50" con espacios normales (Intl usa espacios finos). */
export const texto = (t: string | null) => (t ?? '').replace(/\s/g, ' ')
