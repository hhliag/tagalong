// /confirm: tap a ring to cycle grey (pending) -> green (confirmed) -> red (rejected) -> grey.
// Drag a ring to move it; the new spot is saved. "Done" unlocks when nothing is grey.
const chairId = document.body.dataset.chair;
const NEXT = { pending: "confirmed", confirmed: "rejected", rejected: "pending" };
const STATUSES = Object.keys(NEXT);
const DRAG_PX = 6; // a press that moves less than this is a tap

function statusOf(el) {
  return STATUSES.find((s) => el.classList.contains(s)) || "pending";
}

async function cycle(el) {
  const id = el.dataset.id;
  const status = NEXT[statusOf(el)];
  const res = await fetch(`/api/labels/${chairId}/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) return;
  const data = await res.json();
  document.querySelectorAll(`#dot-${id}, #box-${id}`).forEach((d) => {
    d.classList.remove(...STATUSES);
    d.classList.add(status);
  });
  el.setAttribute("aria-label", status);
  document.getElementById("done").classList.toggle("disabled", data.pending > 0);
}

async function move(pin, x, y) {
  const res = await fetch(`/api/labels/${chairId}/${pin.dataset.id}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ x, y }),
  });
  if (!res.ok) return;
  const data = await res.json();
  const box = document.getElementById("box-" + pin.dataset.id);
  if (box && data.box) {
    const [x0, y0] = data.box;
    Object.assign(box.style, { left: x0 * 100 + "%", top: y0 * 100 + "%" });
  }
}

document.querySelectorAll(".pin[data-id]").forEach((pin) => {
  let start = null;

  pin.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    pin.setPointerCapture(e.pointerId);
    const frame = pin.parentElement.getBoundingClientRect();
    start = { px: e.clientX, py: e.clientY, frame, dragging: false,
              x: parseFloat(pin.style.left) / 100, y: parseFloat(pin.style.top) / 100 };
  });

  pin.addEventListener("pointermove", (e) => {
    if (!start) return;
    const dx = e.clientX - start.px, dy = e.clientY - start.py;
    if (!start.dragging && Math.hypot(dx, dy) < DRAG_PX) return;
    start.dragging = true;
    pin.classList.add("dragging");
    const x = Math.min(1, Math.max(0, start.x + dx / start.frame.width));
    const y = Math.min(1, Math.max(0, start.y + dy / start.frame.height));
    pin.style.left = x * 100 + "%";
    pin.style.top = y * 100 + "%";
    const box = document.getElementById("box-" + pin.dataset.id);
    if (box) {
      box.style.transform = `translate(${dx}px, ${dy}px)`;
    }
  });

  const end = (e, cancelled) => {
    if (!start) return;
    const s = start;
    start = null;
    pin.classList.remove("dragging");
    const box = document.getElementById("box-" + pin.dataset.id);
    if (box) box.style.transform = "";
    if (s.dragging && !cancelled) {
      move(pin, parseFloat(pin.style.left) / 100, parseFloat(pin.style.top) / 100);
    } else if (s.dragging) {
      pin.style.left = s.x * 100 + "%";
      pin.style.top = s.y * 100 + "%";
    } else if (!cancelled) {
      cycle(pin);
    }
  };
  pin.addEventListener("pointerup", (e) => end(e, false));
  pin.addEventListener("pointercancel", (e) => end(e, true));

  pin.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      cycle(pin);
    }
  });
});

// Zones that show on no photo: a chip with the same tap cycle.
document.querySelectorAll(".pin-chip[data-id]").forEach((chip) => {
  chip.addEventListener("click", () => cycle(chip));
});

// "Check all": every ring and chip turns green at once.
document.getElementById("check-all").addEventListener("click", async () => {
  const res = await fetch(`/api/labels/${chairId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "confirmed" }),
  });
  if (!res.ok) return;
  document.querySelectorAll(".pin[data-id], .pin-chip[data-id], .zone-box").forEach((d) => {
    d.classList.remove(...STATUSES);
    d.classList.add("confirmed");
    if (d.dataset.id) d.setAttribute("aria-label", "confirmed");
  });
  document.getElementById("done").classList.toggle("disabled", false);
});
