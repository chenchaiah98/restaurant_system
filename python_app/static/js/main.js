// Clean, single-file front-end cart logic
let cart = [];

function loadCart() {
  try {
    cart = JSON.parse(localStorage.getItem("cart") || "[]");
  } catch {
    cart = [];
  }
}

function saveCart() {
  localStorage.setItem("cart", JSON.stringify(cart));
}

function renderCart() {
  loadCart();
  const el = document.getElementById("cart");
  if (!el) return; // if cart element missing, nothing to render
  if (!cart.length) {
    el.innerHTML = '<li class="list-group-item">Cart is empty</li>';
    return;
  }
  // build a quick menu map to reflect latest prices if available
  const menuMap = (window.__MENU__ || []).reduce((acc, it) => {
    acc[it.id] = it;
    return acc;
  }, {});

  el.innerHTML = cart
    .map(
      (c, i) => `
    <li class="list-group-item d-flex justify-content-between align-items-center">
      <div>
        <div class="fw-bold">${c.name}</div>
        <div class="text-muted small">₹${Number(
          menuMap[c.id] && menuMap[c.id].price ? menuMap[c.id].price : c.price
        ).toFixed(2)}</div>
      </div>
      <div>
        <button class="btn btn-sm btn-outline-secondary" onclick="dec(${i})">-</button>
        <span class="mx-2">${c.qty || 1}</span>
        <button class="btn btn-sm btn-outline-secondary" onclick="inc(${i})">+</button>
        <button class="btn btn-sm btn-danger ms-2" onclick="rem(${i})">Remove</button>
      </div>
    </li>`
    )
    .join("");
}

// update stored cart prices from latest menu (called by index polling)
window.updateCartPrices = function () {
  loadCart();
  const menuMap = (window.__MENU__ || []).reduce((acc, it) => {
    acc[it.id] = it;
    return acc;
  }, {});
  let changed = false;
  cart.forEach((c) => {
    if (menuMap[c.id] && Number(menuMap[c.id].price) !== Number(c.price)) {
      c.price = Number(menuMap[c.id].price);
      changed = true;
    }
  });
  if (changed) {
    saveCart();
  }
  renderCart();
};

function inc(i) {
  const id = cart[i].id;
  const menuMap = (window.__MENU__ || []).reduce((acc, it) => {
    acc[it.id] = it;
    return acc;
  }, {});
  const maxQty = menuMap[id] ? menuMap[id].max_qty || 10 : 10;
  cart[i].qty = Math.min(maxQty, (cart[i].qty || 1) + 1);
  saveCart();
  renderCart();
}
function dec(i) {
  cart[i].qty = Math.max(1, (cart[i].qty || 1) - 1);
  saveCart();
  renderCart();
}
function rem(i) {
  cart.splice(i, 1);
  saveCart();
  renderCart();
}

document.addEventListener("click", function (e) {
  if (e.target.matches(".add-btn")) {
    const id = Number(e.target.dataset.id);
    const name = e.target.dataset.name;
    const price = Number(e.target.dataset.price || 0);
    loadCart();
    const found = cart.find((c) => c.id === id);
    const menuMap = (window.__MENU__ || []).reduce((acc, it) => {
      acc[it.id] = it;
      return acc;
    }, {});
    const maxQty = menuMap[id] ? menuMap[id].max_qty || 10 : 10;
    if (found) {
      if ((found.qty || 1) < maxQty) found.qty = (found.qty || 1) + 1;
    } else {
      cart.push({ id, name, price, qty: 1 });
    }
    saveCart();
    renderCart();
  }
});

const reviewBtn = document.getElementById("reviewOrder");
if (reviewBtn)
  reviewBtn.addEventListener("click", () => {
    location.href = "/summary";
  });

// Backwards-compatible placeOrder handler (menu page may not use it anymore)
const placeBtn = document.getElementById("placeOrder");
if (placeBtn) {
  placeBtn.addEventListener("click", async function () {
    loadCart();
    if (!cart.length) return alert("Cart is empty");
    const tableEl = document.getElementById("table");
    const table = tableEl ? tableEl.value.trim() : "";
    const items = cart.map((c) => ({ id: c.id, name: c.name, qty: c.qty }));
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table, items }),
    });
    if (res.status === 201) {
      document.getElementById("msg").innerHTML =
        '<div class="alert alert-success">Order placed</div>';
      cart = [];
      saveCart();
      renderCart();
      setTimeout(() => (document.getElementById("msg").innerHTML = ""), 2000);
    } else {
      const j = await res.json().catch(() => ({}));
      let html =
        '<div class="alert alert-danger">' + (j.error || "Failed") + "</div>";
      if (j.details && Array.isArray(j.details) && j.details.length) {
        html +=
          '<div class="alert alert-warning"><strong>Issues:</strong><ul>' +
          j.details.map((d) => `<li>${d}</li>`).join("") +
          "</ul></div>";
      }
      document.getElementById("msg").innerHTML = html;
    }
  });
}

// initial render
renderCart();
