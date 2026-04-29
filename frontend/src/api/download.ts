export function filenameFromContentDisposition(cd: string | null | undefined): string | null {
  const dispo = cd || ''
  // RFC 5987: filename*=UTF-8''...
  const m1 = dispo.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)
  if (m1?.[1]) {
    try {
      return decodeURIComponent(m1[1].trim())
    } catch {
      return m1[1].trim()
    }
  }
  const m2 = dispo.match(/filename\s*=\s*\"?([^\";]+)\"?/i)
  return m2?.[1]?.trim() || null
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

