import { esc } from "../lib/escape";
import { loginSession } from "../api/mobile";
import { mapLoginError, saveSession } from "../auth/session";
import { getBaseUrl } from "../api/client";
import type { MobileAccount } from "../types";

const isLocal =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

export function renderWelcome(
  root: HTMLElement,
  opts: {
    message?: string;
    isError?: boolean;
    onSuccess: (account: MobileAccount) => void;
  }
) {
  root.innerHTML = `
    <div class="gate-screen">
      <div class="gate-brand">
        <img class="gate-logo" src="/icons/splash-logo.png" alt="FrogsWork" width="96" height="96">
        <p class="gate-tagline">Sales invoicing for Australian sole traders</p>
      </div>
      <section class="panel gate-card">
        <p id="welcome-message" class="${opts.isError ? "error-text" : "hint"}">${esc(
          opts.message || "Sign in with your Cloud subscription to use the mobile app."
        )}</p>
        <form id="welcome-form" class="gate-login-form" novalidate>
          <div class="field"><label for="welcome-email">Email</label><input id="welcome-email" type="email" autocomplete="username" inputmode="email"></div>
          <div class="field"><label for="welcome-password">Password</label><input id="welcome-password" type="password" autocomplete="current-password"></div>
          <div class="btn-row"><button type="button" id="welcome-submit" class="btn primary btn-block">Sign in</button></div>
        </form>
        <p class="hint gate-subscribe"><a href="https://frogswork.com/account/forgot-password.html">Forgot password?</a></p>
        <p class="hint gate-subscribe">Need a subscription? <a href="https://frogswork.com/account/signup.html">Create account →</a></p>
        ${isLocal ? `<p class="hint">API: ${esc(getBaseUrl())}</p>` : ""}
      </section>
      <footer class="gate-footer">
        <a href="https://korraone.com" target="_blank" rel="noopener">KorraOne</a>
        ·
        <a href="https://frogswork.com" target="_blank" rel="noopener">frogswork.com</a>
      </footer>
    </div>`;

  const msg = root.querySelector("#welcome-message") as HTMLElement;
  const submit = root.querySelector("#welcome-submit") as HTMLButtonElement;

  const doLogin = async () => {
    const email = (root.querySelector("#welcome-email") as HTMLInputElement).value.trim();
    const password = (root.querySelector("#welcome-password") as HTMLInputElement).value;
    if (!email || !password) {
      msg.textContent = "Enter your email and password.";
      msg.className = "error-text";
      return;
    }
    submit.disabled = true;
    msg.textContent = "Signing in…";
    msg.className = "hint";
    try {
      const res = await loginSession(email, password);
      saveSession({ access_token: res.access_token, refresh_token: res.refresh_token });
      opts.onSuccess(res.account);
    } catch (err) {
      msg.textContent = mapLoginError(err instanceof Error ? err.message : "Sign in failed.");
      msg.className = "error-text";
    } finally {
      submit.disabled = false;
    }
  };

  submit.addEventListener("click", doLogin);
  root.querySelector("#welcome-form")?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      e.preventDefault();
      doLogin();
    }
  });
}
