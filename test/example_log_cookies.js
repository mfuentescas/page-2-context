// Logs all cookies accessible from the current page context.
// Note: HttpOnly cookies are not exposed to JavaScript and cannot be listed here.

const raw = document.cookie || "";

if (!raw.trim()) {
  console.log("[cookies] No accessible cookies found for this page.");
  return { count: 0, cookies: [] };
}

const cookies = raw
  .split(";")
  .map((part) => part.trim())
  .filter(Boolean)
  .map((part) => {
    const eqIdx = part.indexOf("=");
    if (eqIdx === -1) {
      return { name: part, value: "" };
    }
    return {
      name: part.slice(0, eqIdx),
      value: part.slice(eqIdx + 1),
    };
  });

console.log(`[cookies] Total accessible cookies: ${cookies.length}`);
for (const c of cookies) {
  console.log(`[cookie] ${c.name}=${c.value}`);
}

return { count: cookies.length, cookies };

