/**
 * Enterprise auth view — inline login form rendered into a given container.
 * Exposes TV.enterpriseAuthView.mount(container, { onSuccess, onSwitchToConsumer }).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const ENT_BASE = "https://velocityenterprise.toteminteractive.in";
  const LOGIN_ENDPOINT = "/backend/auth/login";
  const FORGOT_PASSWORD_URL = `${ENT_BASE}/frontend/`;

  function createLoginForm() {
    const wrap = document.createElement("div");
    wrap.className = "ent-auth-view";
    wrap.innerHTML = `
      <div class="ent-auth-card">
        <div class="ent-auth-header">
          <span class="ent-badge">Enterprise</span>
          <h2 class="ent-auth-title">Velocity Enterprise</h2>
        </div>
        <form id="entLoginForm" class="ent-login-form" novalidate>
          <div class="ent-field">
            <label for="entEmail" class="ent-label">Email</label>
            <input id="entEmail" type="email" class="ent-input" autocomplete="email"
                   placeholder="you@company.com" required />
          </div>
          <div class="ent-field">
            <label for="entPassword" class="ent-label">Password</label>
            <input id="entPassword" type="password" class="ent-input"
                   autocomplete="current-password" placeholder="Password" required />
          </div>
          <div id="entLoginError" class="ent-error" role="alert" style="display:none"></div>
          <button type="submit" id="entLoginBtn" class="ent-btn ent-btn--primary">Login</button>
        </form>
        <div class="ent-auth-footer">
          <a id="entForgotLink" href="#" class="ent-link">Forgot password?</a>
          <button type="button" id="entBackBtn" class="ent-link ent-link--btn">
            ← Back to consumer
          </button>
        </div>
      </div>
    `;
    return wrap;
  }

  function showError(errEl, msg) {
    errEl.textContent = msg;
    errEl.style.display = "block";
  }

  function hideError(errEl) {
    errEl.textContent = "";
    errEl.style.display = "none";
  }

  /**
   * Mount the auth view into `container`.
   * @param {HTMLElement} container
   * @param {{ onSuccess: function, onSwitchToConsumer: function }} callbacks
   */
  function mount(container, callbacks) {
    container.innerHTML = "";
    const form = createLoginForm();
    container.appendChild(form);

    const loginForm     = form.querySelector("#entLoginForm");
    const emailInput    = form.querySelector("#entEmail");
    const passwordInput = form.querySelector("#entPassword");
    const loginBtn      = form.querySelector("#entLoginBtn");
    const errEl         = form.querySelector("#entLoginError");
    const forgotLink    = form.querySelector("#entForgotLink");
    const backBtn       = form.querySelector("#entBackBtn");

    forgotLink.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: FORGOT_PASSWORD_URL });
    });

    backBtn.addEventListener("click", () => {
      if (callbacks && typeof callbacks.onSwitchToConsumer === "function") {
        callbacks.onSwitchToConsumer();
      }
    });

    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideError(errEl);
      const email    = emailInput.value.trim();
      const password = passwordInput.value;
      if (!email || !password) {
        showError(errEl, "Email and password are required.");
        return;
      }
      loginBtn.disabled = true;
      loginBtn.textContent = "Logging in…";
      try {
        const res = await fetch(`${ENT_BASE}${LOGIN_ENDPOINT}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = json.message || json.error || `Login failed (${res.status})`;
          showError(errEl, msg);
          return;
        }
        if (!json.accessToken || !json.refreshToken) {
          showError(errEl, "Unexpected server response. Please try again.");
          return;
        }
        if (callbacks && typeof callbacks.onSuccess === "function") {
          callbacks.onSuccess({
            accessToken:  json.accessToken,
            refreshToken: json.refreshToken,
            expiresIn:    json.expiresIn || 900,
            user:         json.user || {},
          });
        }
      } catch (err) {
        showError(errEl, "Network error. Check your connection and try again.");
      } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = "Login";
      }
    });
  }

  root.TV.enterpriseAuthView = { mount };
})();
