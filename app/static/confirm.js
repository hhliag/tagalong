// /confirm: ✓ turns the dot jade, ✗ hides it. "Done" unlocks when every label is decided.
const chairId = document.body.dataset.chair;

document.querySelectorAll(".decide button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const n = btn.dataset.n;
    const status = btn.dataset.status;
    const res = await fetch(`/api/labels/${chairId}/${n}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("row-" + n).className = "decide " + status;
    document.querySelectorAll(`#row-${n} .dot, #row-${n} .zone-mark, #dot-${n}, #box-${n}`).forEach((d) => {
      d.classList.remove("pending", "confirmed", "rejected");
      d.classList.add(status);
    });
    document.getElementById("done").classList.toggle("disabled", data.pending > 0);
  });
});
