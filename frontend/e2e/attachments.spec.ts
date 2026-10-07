import { test, expect } from '@playwright/test'

test('upload, select, ask with sources and remove an attachment', async ({ page }) => {
  const conversation = '00000000-0000-0000-0000-000000000002'
  const item = { attachment_id: '00000000-0000-0000-0000-000000000001', conversation_id: conversation, filename: 'ventas.csv', kind: 'table', size_bytes: 25, warnings: [] }
  let uploaded = false
  await page.addInitScript(() => localStorage.setItem('yitetsuai_token', 'test-session'))
  await page.route('http://127.0.0.1:8001/**', async route => {
    const request = route.request(); const url = new URL(request.url())
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    let json: unknown = {}
    if (url.pathname === '/health') json = { status: 'ok' }
    if (url.pathname === '/ai/capabilities') json = {
      count: 10,
      components: Array.from({ length: 10 }, (_, index) => ({
        id: `component-${index}`,
        name: `Component ${index + 1}`,
        function: 'Test capability',
        implementation: 'Test',
        availability: 'integrated',
      })),
    }
    if (url.pathname === '/users/me') json = { user_id: 'user', email: 'test@example.test', full_name: 'Test User' }
    if (url.pathname === '/conversations') json = uploaded ? [{ conversation_id: conversation, title: 'ventas.csv', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 0 }] : []
    if (url.pathname === '/attachments' && request.method() === 'POST') {
      expect(request.headers()['content-type']).toContain('multipart/form-data; boundary=')
      expect(request.headers().authorization).toBe('Bearer test-session')
      uploaded = true; json = item
    } else if (url.pathname === '/attachments') json = uploaded ? [item] : []
    if (request.method() === 'DELETE') { uploaded = false; return route.fulfill({ status: 204, headers }) }
    if (url.pathname === '/chat') {
      expect(request.postDataJSON().attachment_ids).toEqual([item.attachment_id])
      expect(request.postDataJSON().conversation_id).toBe(conversation)
      json = { corrections: [], interpreted_prompt: 'Compara ingresos', response: 'Los ingresos suman 30.', conversation_id: conversation, warnings: [], messages: [{ role: 'user', content: 'Compara ingresos' }, { role: 'assistant', content: 'Los ingresos suman 30.', sources: [{ attachment_id: item.attachment_id, filename: item.filename, locator: 'tabla, resumen', excerpt: 'sum=30' }] }] }
    }
    return route.fulfill({ json, headers, status: request.method() === 'POST' && url.pathname === '/attachments' ? 201 : 200 })
  })
  await page.goto('/')
  await expect(page.getByText('Test User', { exact: true })).toBeVisible()
  await expect(page.getByText('10 componentes especializados')).toBeVisible()
  await page.locator('input[type=file]').setInputFiles({ name: 'ventas.csv', mimeType: 'text/csv', buffer: Buffer.from('name,total\nAurora,30') })
  await expect(page.getByRole('checkbox')).toBeChecked()
  await page.getByRole('textbox').fill('Compara ingresos')
  await page.getByRole('button', { name: 'Consultar IA', exact: true }).click()
  await expect(page.getByText('Los ingresos suman 30.', { exact: true })).toBeVisible()
  await page.getByText('Fuentes aportadas al modelo (1)').click()
  await expect(page.getByText('sum=30', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Eliminar', exact: true }).click()
  await expect(page.getByRole('checkbox')).toHaveCount(0)
})

test('guest cannot upload files', async ({ page }) => {
  await page.route('http://127.0.0.1:8001/**', route => route.fulfill({
    json: route.request().url().endsWith('/health')
      ? { status: 'ok' }
      : {
          count: 10,
          components: Array.from({ length: 10 }, (_, index) => ({
            id: `component-${index}`,
            name: `Component ${index + 1}`,
            function: 'Test capability',
            implementation: 'Test',
            availability: 'integrated',
          })),
        },
    headers: { 'access-control-allow-origin': '*' },
  }))
  await page.goto('/')
  await expect(page.locator('input[type=file]')).toBeDisabled()
})
