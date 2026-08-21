// 运行时解析部署 base（任意子路径部署无需重新构建）
export function resolveBase(): string {
  const raw: string = import.meta.env.BASE_URL
  // 显式绝对子路径（如 GitHub CI 的 /DLiteQuant/）→ 直接用
  if (raw.startsWith('/') && raw !== '/') return raw
  // 相对部署：从入口脚本实际 URL 推断部署目录（.../assets/index-xxx.js → .../）
  const entry = Array.from(document.querySelectorAll('script[src]')).find((s) =>
    (s as HTMLScriptElement).src.includes('/assets/index-'),
  )
  if (entry) {
    const src = (entry as HTMLScriptElement).src
    const idx = src.lastIndexOf('/assets/')
    if (idx > 0) return src.slice(0, idx + 1)
  }
  return '/'
}
