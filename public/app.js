document.getElementById("rok").textContent = new Date().getFullYear();

// Pricing buttons preselect the package in the contact form
document.querySelectorAll("[data-pakiet]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelector('select[name="pakiet"]').value = btn.dataset.pakiet;
  });
});

const form = document.getElementById("form");
const status = document.getElementById("status");

function setStatus(text, kind) {
  status.textContent = text;
  status.className = "status " + (kind || "");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  form.querySelectorAll(".invalid").forEach((el) => el.classList.remove("invalid"));

  const invalid = [...form.querySelectorAll("[required]")].filter((el) => !el.checkValidity());
  if (invalid.length) {
    invalid.forEach((el) => el.classList.add("invalid"));
    invalid[0].focus();
    setStatus("Uzupełnij pola oznaczone gwiazdką i zaznacz zgodę.", "err");
    return;
  }

  const data = Object.fromEntries(new FormData(form));
  data.zgoda = form.zgoda.checked;
  const button = form.querySelector("button");
  button.disabled = true;
  setStatus("Wysyłanie…");

  try {
    const res = await fetch("/api/kontakt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || "Błąd serwera");
    form.reset();
    setStatus("Dziękuję! Wiadomość wysłana – odezwę się w ciągu 24 godzin.", "ok");
  } catch (err) {
    setStatus(err.message + ". Spróbuj ponownie lub napisz na e-mail.", "err");
  } finally {
    button.disabled = false;
  }
});
