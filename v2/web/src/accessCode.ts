const KEY = 'onetouch_access_token';

export function readAccessCode(): string {
  try {
    const saved = localStorage.getItem(KEY);
    const legacy = sessionStorage.getItem(KEY);
    if (saved !== null) {
      sessionStorage.removeItem(KEY);
      return saved;
    }
    if (legacy) {
      localStorage.setItem(KEY, legacy);
      sessionStorage.removeItem(KEY);
      return legacy;
    }
  } catch { /* Restricted storage: the current tab can still connect. */ }
  return '';
}

export function saveAccessCode(value: string): void {
  // Persist an empty value as well, so an older tab cannot restore a deleted code.
  localStorage.setItem(KEY, value.trim());
  sessionStorage.removeItem(KEY);
}
