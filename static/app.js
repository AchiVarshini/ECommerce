const API = "";
const photoSets = {
  Electronics: ["photo-1505740420928-5e560c06d30e", "photo-1523275335684-37898b6baf30", "photo-1608043152269-423dbba4e7e1", "photo-1544244015-0df4b3ffc6b0", "photo-1625842268584-8f3296236761", "photo-1587829741301-dc798b83add3"],
  Home: ["photo-1578500494198-246f612d3b3d", "photo-1616486338812-3dadae4b4ace", "photo-1507473885765-e6ed057f782c", "photo-1594620302200-9a762244a156", "photo-1602143407151-7111542de6e8", "photo-1556911220-bff31c812dba"],
  Fashion: ["photo-1542291026-7eec264c27ff", "photo-1627123424574-724758594e93", "photo-1590874103328-eac38a683ce7", "photo-1601924994987-69e26d50dc26", "photo-1543076447-215ad9ba6923", "photo-1576053139778-7e32f2ae3cfd"],
  Beauty: ["photo-1608248543803-ba4f8c70ae0b", "photo-1601049541289-9b1b7bbbfe19", "photo-1608571423902-eed4a5ad8108", "photo-1556229010-6c3f2c9ca5f8"],
  Sports: ["photo-1544367567-0f2fcb009e0b", "photo-1517836357463-d25dfeac3438", "photo-1576678927484-cc907957088c", "photo-1518611012118-696072aa579a"],
  Books: ["photo-1544947950-fa07a98d237f", "photo-1512820790803-83ca734da794", "photo-1519682337058-a94d519337bc", "photo-1543002588-bfa74002ed7e"]
};
const photoFor = (product) => {
  const choices = photoSets[product.category] || photoSets.Home;
  const index = Math.abs(Number(product.product_id) * 7 + String(product.product_name).length) % choices.length;
  return `https://images.unsplash.com/${choices[index]}?auto=format&fit=crop&w=650&q=78`;
};
const state = { token: localStorage.getItem("smartcart_token"), customer: JSON.parse(localStorage.getItem("smartcart_customer") || "null"), products: [], category: "", query: "", cart: [], mode: "login", toastTimer: null };
const $ = (selector) => document.querySelector(selector);
const money = (amount) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(amount || 0));

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}), ...(options.headers || {}) };
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}

function notify(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("visible"), 2900);
}

function showView(name) {
  $("#shop-view").classList.toggle("hidden", name !== "shop");
  $("#account-view").classList.toggle("hidden", name !== "account");
  $("#admin-view").classList.toggle("hidden", name !== "admin");
  document.querySelectorAll(".nav-link").forEach((button) => button.classList.remove("active"));
  if (name === "shop") $("#shop-nav").classList.add("active");
  if (name === "account") $("#account-nav").classList.add("active");
  if (name === "admin") $("#admin-nav").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateIdentity() {
  const signedIn = Boolean(state.customer && state.token);
  $("#auth-button").textContent = signedIn ? `Hi, ${state.customer.name.split(" ")[0]}` : "Sign in ↗";
  $("#account-nav").classList.toggle("hidden", !signedIn || state.customer.role === "admin");
  $("#admin-nav").classList.toggle("hidden", !signedIn || state.customer.role !== "admin");
  $("#signout-button").classList.toggle("hidden", !signedIn);
  $("#footer-status").textContent = signedIn ? `WELCOME BACK, ${state.customer.name.toUpperCase()}` : "SHOP SMARTER, EVERY DAY";
}

function productCard(product, index) {
  return `<article class="product-card" style="animation-delay:${Math.min(index * 28, 280)}ms">
    <div class="product-visual"><img src="${photoFor(product)}" alt="${escapeHtml(product.product_name)}" loading="lazy" onerror="this.src='https://images.unsplash.com/photo-1490312278390-ab64016e0aa9?auto=format&fit=crop&w=650&q=78'"><span class="product-category">${escapeHtml(product.category)}</span><button class="wishlist-button" data-wishlist="${product.product_id}" title="Save to wishlist" aria-label="Save ${escapeHtml(product.product_name)} to wishlist">♡</button><button class="quick-add" data-add="${product.product_id}">Add to bag <span>+</span></button></div>
    <div class="product-info"><div class="product-title-row"><span class="product-name">${escapeHtml(product.product_name)}</span><span class="product-price">${money(product.price)}</span></div><div class="product-meta"><span>${product.stock > 0 ? `${product.stock} in stock` : "Currently sold out"}</span><span class="rating">★ ${Number(product.rating).toFixed(1)}</span></div></div>
  </article>`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function renderCategories(products) {
  const categories = [...new Set(products.map((product) => product.category))].sort();
  $("#category-list").innerHTML = `<button class="filter-item ${state.category === "" ? "selected" : ""}" data-category="">All products<span class="filter-count">${products.length}</span></button>${categories.map((category) => `<button class="filter-item ${state.category === category ? "selected" : ""}" data-category="${escapeHtml(category)}">${escapeHtml(category)}<span class="filter-count">${products.filter((product) => product.category === category).length}</span></button>`).join("")}`;
  $("#all-count").textContent = products.length;
}

async function loadProducts() {
  const params = new URLSearchParams({ sort: $("#sort").value });
  if (state.query) params.set("search", state.query);
  if (state.category) params.set("category", state.category);
  try {
    const products = await request(`/products?${params}`);
    state.products = products;
    const allProducts = state.category || state.query ? await request("/products") : products;
    renderCategories(allProducts);
    $("#products").innerHTML = products.map(productCard).join("");
    $("#result-count").textContent = `${products.length} thoughtfully found ${products.length === 1 ? "piece" : "pieces"}`;
    $("#empty-state").classList.toggle("hidden", products.length > 0);
  } catch (error) { notify(error.message); }
}

function openAuth(mode = "login") {
  setAuthMode(mode);
  $("#auth-message").textContent = "";
  $("#auth-modal").classList.remove("hidden");
}

function setAuthMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".auth-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.mode === mode));
  ["name", "city", "age"].forEach((field) => $(`#${field}-field`).classList.toggle("hidden", mode !== "register"));
  $("#auth-title").innerHTML = mode === "login" ? "Find your <em>way in.</em>" : "Make it <em>yours.</em>";
  $("#auth-submit-label").textContent = mode === "login" ? "Sign in" : "Create account";
  $("#auth-form [name=password]").autocomplete = mode === "login" ? "current-password" : "new-password";
}

async function signIn(email, password) {
  const result = await request("/login", { method: "POST", body: JSON.stringify({ email, password }) });
  state.token = result.access_token;
  state.customer = result.customer;
  localStorage.setItem("smartcart_token", state.token);
  localStorage.setItem("smartcart_customer", JSON.stringify(state.customer));
  $("#auth-modal").classList.add("hidden");
  updateIdentity();
  await loadCart();
  showView(state.customer.role === "admin" ? "admin" : "account");
  if (state.customer.role === "admin") await loadAdmin(); else await loadDashboard();
  notify(`Welcome in, ${state.customer.name.split(" ")[0]}.`);
}

async function loadCart() {
  if (!state.customer || state.customer.role === "admin") { state.cart = []; renderCart(); return; }
  const result = await request(`/cart/${state.customer.customer_id}`);
  state.cart = result.items;
  renderCart(result.total);
}

function renderCart(total = null) {
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  $("#cart-count").textContent = count;
  $("#drawer-count").textContent = `(${count})`;
  $("#cart-total").textContent = money(total ?? state.cart.reduce((sum, item) => sum + item.price * item.quantity, 0));
  $("#cart-items").innerHTML = state.cart.length ? state.cart.map((item) => `<div class="cart-line"><img src="${photoFor({ ...item, product_name: item.product_name })}" alt=""><div><h3>${escapeHtml(item.product_name)}</h3><p>${item.quantity} × ${money(item.price)}</p><button data-remove="${item.cart_id}">Remove</button></div><strong>${money(item.line_total)}</strong></div>`).join("") : `<div class="cart-empty">Your bag is taking a little breather.</div>`;
  $("#checkout-button").disabled = !state.cart.length;
  $("#checkout-button").style.opacity = state.cart.length ? "1" : ".55";
}

async function loadDashboard() {
  if (!state.customer || state.customer.role === "admin") return;
  $("#dashboard").innerHTML = `<div class="loading-line">Gathering your picks...</div>`;
  try {
    const dashboard = await request(`/customer-dashboard/${state.customer.customer_id}`);
    const customer = dashboard.customer;
    $("#dashboard").innerHTML = `<div class="welcome-line"><div><h2>Good to see you, ${escapeHtml(customer.name.split(" ")[0])}.</h2><p>Your next good find is closer than you think.</p></div><span class="segment-pill">${escapeHtml(dashboard.segment)}</span></div>
      <div class="metric-grid"><div class="metric"><span>Lifetime spend</span><strong>${money(dashboard.total_spending)}</strong></div><div class="metric"><span>Orders placed</span><strong>${dashboard.total_orders}</strong></div><div class="metric"><span>Average order</span><strong>${money(dashboard.average_order_value)}</strong></div></div>
      <section class="dashboard-section"><div class="dashboard-section-heading"><div><span class="eyebrow">YOUR PERSONAL EDIT</span><h2>Picked for <em>your kind of good.</em></h2></div><p>Refreshed from what you browse and love</p></div><div class="recommend-grid">${dashboard.recommendations.map((product, index) => `<article class="recommend-card"><img src="${photoFor(product)}" alt="${escapeHtml(product.product_name)}" loading="lazy"><div class="recommend-card-body"><h3>${escapeHtml(product.product_name)}</h3><p>${escapeHtml(product.category)} · ${money(product.price)}</p><button class="primary-button" data-add="${product.product_id}">Add to bag <span>+</span></button></div></article>`).join("")}</div></section>
      <section class="dashboard-section"><div class="dashboard-section-heading"><div><span class="eyebrow">PURCHASE INTELLIGENCE</span><h2>Signals for your <em>next find.</em></h2></div><p>Model probability, based on your activity</p></div><div class="signal-list">${dashboard.purchase_predictions.map((prediction) => `<div class="signal-row"><span>${escapeHtml(prediction.product_name)}</span><span>${Math.round(prediction.purchase_probability * 100)}% match</span><span>${prediction.purchase_probability >= .5 ? "Likely to purchase" : "Worth a closer look"}</span></div>`).join("")}</div></section>
      <section class="dashboard-section"><div class="dashboard-section-heading"><div><span class="eyebrow">YOUR RECENT ORDERS</span><h2>What you have <em>loved so far.</em></h2></div></div><div id="recent-orders" class="signal-list"><div class="loading-line">Loading orders...</div></div></section>`;
    const orders = await request(`/customers/${customer.customer_id}/orders`);
    $("#recent-orders").innerHTML = orders.slice(0, 4).map((order) => `<div class="signal-row"><span>Order #${order.order_id} · ${order.items.length} ${order.items.length === 1 ? "item" : "items"}</span><span>${money(order.total)}</span><span>${new Date(order.order_date).toLocaleDateString()}</span></div>`).join("") || `<div class="loading-line">Your first order is waiting to happen.</div>`;
  } catch (error) { $("#dashboard").innerHTML = `<p class="loading-line">${escapeHtml(error.message)}</p>`; }
}

function drawChart(canvas, values, labels, color, kind = "bar") {
  if (!canvas || !values.length) return;
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.width = rect.width * scale;
  canvas.height = rect.height * scale;
  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  const width = rect.width, height = rect.height;
  const padding = { top: 10, right: 7, bottom: 35, left: 43 };
  const chartWidth = width - padding.left - padding.right, chartHeight = height - padding.top - padding.bottom;
  const max = Math.max(...values, 1) * 1.15;
  context.font = "9px DM Sans, sans-serif";
  context.textBaseline = "middle";
  for (let line = 0; line < 4; line++) {
    const y = padding.top + chartHeight * line / 3;
    context.strokeStyle = "#e4e8e0"; context.beginPath(); context.moveTo(padding.left, y); context.lineTo(width - padding.right, y); context.stroke();
    context.fillStyle = "#8a948c"; context.textAlign = "right"; context.fillText(money(max * (1 - line / 3)).replace("$", ""), padding.left - 6, y);
  }
  const step = chartWidth / values.length;
  values.forEach((value, index) => {
    const barHeight = Math.max(2, chartHeight * value / max);
    const x = padding.left + step * index + step * .18;
    const y = padding.top + chartHeight - barHeight;
    if (kind === "line") {
      const pointX = x + step * .32, pointY = y;
      if (index) { const prevHeight = chartHeight * values[index - 1] / max; context.strokeStyle = color; context.lineWidth = 2; context.beginPath(); context.moveTo(padding.left + step * (index - .5), padding.top + chartHeight - prevHeight); context.lineTo(pointX, pointY); context.stroke(); }
      context.fillStyle = color; context.beginPath(); context.arc(pointX, pointY, 3, 0, Math.PI * 2); context.fill();
    } else { context.fillStyle = color; context.fillRect(x, y, step * .64, barHeight); }
    context.fillStyle = "#79837c"; context.textAlign = "center";
    const label = String(labels[index] || "");
    context.fillText(label.length > 12 ? `${label.slice(0, 11)}…` : label, x + step * .32, height - 15);
  });
}

async function loadAdmin() {
  $("#admin-dashboard").innerHTML = `<div class="loading-line">Loading store signals...</div>`;
  try {
    const [summary, categories, products, customers, segments, lowStock, eda] = await Promise.all([
      request("/admin/sales-summary"), request("/admin/category-sales"), request("/admin/top-products"), request("/admin/top-customers"), request("/admin/customer-segments"), request("/admin/low-stock-products"), request("/admin/eda")
    ]);
    $("#admin-dashboard").innerHTML = `<div class="admin-stats"><div class="admin-stat"><span>Lifetime revenue</span><strong>${money(summary.revenue)}</strong></div><div class="admin-stat"><span>Orders</span><strong>${summary.orders.toLocaleString()}</strong></div><div class="admin-stat"><span>Average order value</span><strong>${money(summary.average_order_value)}</strong></div><div class="admin-stat"><span>Repeat customers</span><strong>${eda.repeat_customer_percentage}%</strong></div></div>
      <div class="admin-grid"><section class="chart-panel"><h3>Revenue, month by month</h3><canvas id="revenue-chart"></canvas></section><section class="chart-panel"><h3>Category sales</h3><canvas id="category-chart"></canvas></section></div>
      <div class="admin-lists"><section class="admin-list"><h3>Products leading the edit</h3>${products.slice(0, 6).map((product) => `<div class="admin-row"><span>${escapeHtml(product.product_name)}</span><span>${money(product.revenue)}</span></div>`).join("")}</section><section class="admin-list"><h3>Customers making it count</h3>${customers.slice(0, 6).map((customer) => `<div class="admin-row"><span>${escapeHtml(customer.name)} · ${escapeHtml(customer.city)}</span><span>${money(customer.total_spending)}</span></div>`).join("")}</section><section class="admin-list"><h3>Customer segments</h3>${segments.map((segment) => `<div class="admin-row"><span>${escapeHtml(segment.segment)}</span><span>${segment.customers} customers</span></div>`).join("")}</section><section class="admin-list"><h3>Running low</h3>${lowStock.slice(0, 6).map((product) => `<div class="admin-row"><span>${escapeHtml(product.product_name)}</span><span>${product.stock} left</span></div>`).join("") || `<div class="admin-row"><span>Everything is well stocked</span></div>`}</section></div>`;
    drawChart($("#revenue-chart"), summary.monthly_revenue.slice(-12).map((row) => row.revenue), summary.monthly_revenue.slice(-12).map((row) => row.month.slice(2)), "#e87c5b", "line");
    drawChart($("#category-chart"), categories.map((row) => row.revenue), categories.map((row) => row.category), "#174d3d");
  } catch (error) { $("#admin-dashboard").innerHTML = `<p class="loading-line">${escapeHtml(error.message)}</p>`; }
}

document.addEventListener("click", async (event) => {
  const category = event.target.closest("[data-category]");
  if (category) { state.category = category.dataset.category; $("#catalog-title").innerHTML = state.category ? `${escapeHtml(state.category)} <em>worth finding.</em>` : "Find your <em>next favorite.</em>"; await loadProducts(); }
  const addButton = event.target.closest("[data-add]");
  if (addButton) {
    if (!state.customer || state.customer.role === "admin") { openAuth(); return; }
    try {
      await request("/cart", { method: "POST", body: JSON.stringify({ customer_id: state.customer.customer_id, product_id: Number(addButton.dataset.add), quantity: 1 }) });
      await loadCart(); notify("A good find, added to your bag.");
    } catch (error) { notify(error.message); }
  }
  const wishlist = event.target.closest("[data-wishlist]");
  if (wishlist) {
    if (!state.customer) { openAuth(); return; }
    try { await request(`/wishlist/${wishlist.dataset.wishlist}`, { method: "POST" }); wishlist.classList.add("saved"); wishlist.textContent = "♥"; notify("Saved to your wishlist."); }
    catch (error) { notify(error.message); }
  }
  const remove = event.target.closest("[data-remove]");
  if (remove) { try { await request(`/cart/${remove.dataset.remove}`, { method: "DELETE" }); await loadCart(); } catch (error) { notify(error.message); } }
});

$("#search").addEventListener("input", (event) => { state.query = event.target.value.trim(); clearTimeout(state.searchTimer); state.searchTimer = setTimeout(loadProducts, 180); });
$("#sort").addEventListener("change", loadProducts);
$("#browse-button").addEventListener("click", () => $("#collection").scrollIntoView({ behavior: "smooth" }));
$("#shop-nav").addEventListener("click", () => showView("shop"));
$("#account-nav").addEventListener("click", async () => { if (!state.customer) return openAuth(); showView("account"); await loadDashboard(); });
$("#admin-nav").addEventListener("click", async () => { showView("admin"); await loadAdmin(); });
$("#auth-button").addEventListener("click", () => state.customer ? (state.customer.role === "admin" ? showView("admin") : showView("account")) : openAuth());
$("#signout-button").addEventListener("click", () => { state.token = null; state.customer = null; state.cart = []; localStorage.removeItem("smartcart_token"); localStorage.removeItem("smartcart_customer"); updateIdentity(); renderCart(); showView("shop"); notify("You are signed out."); });
$("#admin-refresh").addEventListener("click", loadAdmin);
$("#cart-toggle").addEventListener("click", async () => { if (!state.customer || state.customer.role === "admin") return openAuth(); await loadCart(); $("#cart-drawer").classList.remove("hidden"); });
$("#close-cart").addEventListener("click", () => $("#cart-drawer").classList.add("hidden"));
$("#cart-drawer").addEventListener("click", (event) => { if (event.target === $("#cart-drawer")) $("#cart-drawer").classList.add("hidden"); });
$("#close-auth").addEventListener("click", () => $("#auth-modal").classList.add("hidden"));
$("#auth-modal").addEventListener("click", (event) => { if (event.target === $("#auth-modal")) $("#auth-modal").classList.add("hidden"); });
document.querySelectorAll(".auth-tab").forEach((tab) => tab.addEventListener("click", () => setAuthMode(tab.dataset.mode)));
$("#demo-customer").addEventListener("click", () => signIn("customer1@smartcart.com", "SmartCart123!").catch((error) => { $("#auth-message").textContent = error.message; }));
$("#demo-admin").addEventListener("click", () => signIn("admin@smartcart.com", "Admin123!").catch((error) => { $("#auth-message").textContent = error.message; }));
$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const email = form.get("email"), password = form.get("password");
  $("#auth-message").textContent = "";
  try {
    if (state.mode === "register") {
      const result = await request("/register", { method: "POST", body: JSON.stringify({ name: form.get("name"), email, password, city: form.get("city"), age: Number(form.get("age")), gender: "Prefer not to say" }) });
      await signIn(result.email, password);
    } else await signIn(email, password);
  } catch (error) { $("#auth-message").textContent = error.message; }
});
$("#checkout-button").addEventListener("click", async () => {
  try {
    const order = await request("/orders", { method: "POST", body: JSON.stringify({ payment_method: "Card" }) });
    $("#cart-drawer").classList.add("hidden"); await loadCart(); await loadProducts(); await loadDashboard();
    notify(`Order #${order.order_id} is confirmed. Your picks just got smarter.`);
  } catch (error) { notify(error.message); }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) { event.preventDefault(); $("#search").focus(); }
  if (event.key === "Escape") { $("#auth-modal").classList.add("hidden"); $("#cart-drawer").classList.add("hidden"); }
});
window.addEventListener("resize", () => { if (state.customer?.role === "admin" && !$("#admin-view").classList.contains("hidden")) loadAdmin(); });

async function start() {
  updateIdentity();
  await loadProducts();
  if (state.token && state.customer) {
    try { await request(`/customers/${state.customer.customer_id}`); await loadCart(); }
    catch { state.token = null; state.customer = null; localStorage.removeItem("smartcart_token"); localStorage.removeItem("smartcart_customer"); updateIdentity(); }
  }
}
start();