// /build: run the pipeline one stage at a time so each line ticks (DESIGN §4).
const chairId = document.body.dataset.chair;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function setStage(id, state, detail, tag) {
  const li = document.getElementById("st-" + id);
  li.className = "stage " + state;
  li.querySelector(".detail").textContent = detail || "";
  li.querySelector(".tag").textContent = tag || "";
}

async function stage(id, url) {
  setStage(id, "running", "Working…");
  await sleep(700); // M1 returns saved data instantly; pause so the tick is visible
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(id + ": HTTP " + res.status);
  return res.json();
}

const tagFor = (r) => (r.source === "saved" ? "Saved result" : "");

document.getElementById("go").addEventListener("click", async (e) => {
  e.target.disabled = true;
  e.target.textContent = "Building…";
  document.getElementById("stages").hidden = false;
  try {
    const plate = await stage("plate", "/api/plate/" + chairId);
    setStage("plate", "done", plate.make + " " + plate.model, tagFor(plate));

    const manual = await stage("manual", "/api/manual/" + chairId);
    if (!manual.found) {
      setStage("manual", "failed", manual.message, tagFor(manual));
      const card = document.getElementById("error-card");
      card.textContent = manual.message;
      card.hidden = false;
      return;
    }
    setStage("manual", "done", "Found in library: " + manual.title, tagFor(manual));
    setStage("extract", "skipped", "Found in library: not needed");
    setStage("verify", "skipped", "Found in library: quotes already checked");

    const label = await stage("label", "/api/label/" + chairId);
    setStage("label", "done", label.count + " labels placed", tagFor(label));

    e.target.hidden = true;
    document.getElementById("next").hidden = false;
  } catch (err) {
    const card = document.getElementById("error-card");
    card.textContent = "Something went wrong: " + err.message;
    card.hidden = false;
  }
});
