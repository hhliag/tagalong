// /uses/{chair}/return: the answer is kept in this browser only (DESIGN §7).
const key = "tagalong-return-" + document.body.dataset.chair;
const out = document.getElementById("return-result");
const messages = {
  ok: "Thank you. Your chair is marked as all OK.",
  problem: "A problem is noted. Please tell the crew at the aircraft door.",
};

function show(result) {
  out.textContent = messages[result] || "";
}

try {
  show(localStorage.getItem(key));
} catch (e) {}

document.querySelectorAll("[data-result]").forEach((btn) => {
  btn.addEventListener("click", () => {
    show(btn.dataset.result);
    try {
      localStorage.setItem(key, btn.dataset.result);
    } catch (e) {}
  });
});
