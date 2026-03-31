export function escHtml(str = "") {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

export function formatSize(size = 0) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`;
  if (size > 1024) return `${(size / 1024).toFixed(1)}KB`;
  return `${size}B`;
}

export function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

export function extractUserQuery(text = "") {
  const m = String(text).match(/<user_query>\s*([\s\S]*?)\s*<\/user_query>/i);
  return m?.[1]?.trim() || "";
}

export function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  return Promise.resolve();
}
