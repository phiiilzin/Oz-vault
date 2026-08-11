document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash").forEach((el) => {
    setTimeout(() => { el.style.transition = "opacity .4s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, 4000);
  });
});

function updateTotal(input, unitPrice, targetId) {
  const qty = parseInt(input.value || "1", 10);
  const total = (qty * unitPrice).toFixed(2).replace(".", ",");
  const el = document.getElementById(targetId);
  if (el) el.textContent = "R$ " + total;
}
