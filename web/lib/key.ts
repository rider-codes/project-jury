// The visitor's own API key. It lives in this tab only (sessionStorage, or just memory when the
// browser blocks storage) and goes to the server in a header on each request. It is never put in
// a URL, a cookie or localStorage.
const NAME = "jury_key";
let memory = "";

export function getKey(): string {
  try {
    return sessionStorage.getItem(NAME) ?? memory;
  } catch {
    return memory;
  }
}

export function setKey(key: string) {
  memory = key;
  try {
    if (key) sessionStorage.setItem(NAME, key);
    else sessionStorage.removeItem(NAME);
  } catch {}
}
