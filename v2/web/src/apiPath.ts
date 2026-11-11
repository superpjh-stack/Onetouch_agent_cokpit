export function apiPath(path: string): string {
 const url = new URL(path.replace(/^\//, ''), window.location.href);
 return url.pathname + url.search;
}
