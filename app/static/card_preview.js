// /passport: scale the A5 card (210 x 148 mm) to the page width, so the whole card shows, not cut off.
const frame = document.querySelector(".card-preview-frame");
const inner = frame && frame.querySelector(".card-preview-scale");
function fit() {
  const sheet = inner.firstElementChild;
  const scale = Math.min(1, frame.clientWidth / sheet.offsetWidth);
  inner.style.transform = `scale(${scale})`;
  frame.style.height = sheet.offsetHeight * scale + "px";
}
if (inner) {
  fit();
  window.addEventListener("resize", fit);
}
