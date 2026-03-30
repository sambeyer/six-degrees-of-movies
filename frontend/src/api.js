let connectCtrl = null;

export async function searchActors(q, limit = 15) {
  if (!q || q.length < 2) return [];
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  if (!res.ok) return [];
  return res.json();
}

export async function randomActors() {
  const res = await fetch("/api/random-actors");
  if (!res.ok) return [];
  return res.json();
}

export async function connect(params) {
  if (connectCtrl) connectCtrl.abort();
  connectCtrl = new AbortController();
  const res = await fetch("/api/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal: connectCtrl.signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }
  return res.json();
}
