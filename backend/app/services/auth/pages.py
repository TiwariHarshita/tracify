import secrets

from fastapi.responses import HTMLResponse


def action_page(reset: bool) -> HTMLResponse:
    nonce = secrets.token_urlsafe(18)
    title = "Reset your password" if reset else "Verify your email"
    endpoint = "/api/v1/auth/password/reset" if reset else "/api/v1/auth/email/verify"
    fields = """
      <label>New password <input id="password" type="password"
        autocomplete="new-password" minlength="12" maxlength="128" required></label>
      <label>Confirm password <input id="confirmation" type="password"
        autocomplete="new-password" minlength="12" maxlength="128" required></label>
    """ if reset else "<p>Choose the button below to confirm your email address.</p>"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="referrer" content="no-referrer"><title>Trace — {title}</title>
<style nonce="{nonce}">
body {{ font: 16px system-ui; max-width: 440px; margin: 12vh auto; padding: 20px; color: #18202b; }}
label {{ display: block; margin: 18px 0; }} input {{ display: block; box-sizing: border-box; width: 100%; padding: 10px; margin-top: 8px; }}
button {{ padding: 12px 18px; cursor: pointer; }} #message {{ line-height: 1.5; }}
</style></head><body><p>Trace</p><h1>{title}</h1>
<form id="action" method="post" action="{endpoint}">{fields}
<button id="submit" type="submit">{title}</button></form><p id="message" role="status"></p>
<script nonce="{nonce}">
(() => {{
  const token = new URLSearchParams(location.hash.slice(1)).get("token");
  history.replaceState(null, "", location.pathname);
  const message = document.getElementById("message");
  const button = document.getElementById("submit");
  if (!token) {{ message.textContent = "Open the complete link from your email."; button.disabled = true; }}
  document.getElementById("action").addEventListener("submit", async (event) => {{
    event.preventDefault();
    const body = {{token}};
    const password = document.getElementById("password");
    if (password) {{
      if (password.value !== document.getElementById("confirmation").value) {{
        message.textContent = "Passwords do not match."; return;
      }}
      body.new_password = password.value;
    }}
    button.disabled = true;
    try {{
      const response = await fetch("{endpoint}", {{
        method: "POST", credentials: "same-origin",
        headers: {{"Content-Type": "application/json", "X-Trace-Client": "web"}},
        body: JSON.stringify(body)
      }});
      const data = await response.json();
      message.textContent = response.ok ? data.message :
        (typeof data.detail === "string" ? data.detail : "Check your input and try again.");
      if (!response.ok) button.disabled = false;
      else {{
        document.getElementById("action").reset();
        message.textContent += " You can close this page and sign in.";
      }}
    }} catch (_) {{ message.textContent = "Could not connect. Try again."; button.disabled = false; }}
  }});
}})();
</script></body></html>"""
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            f"default-src 'none'; script-src 'nonce-{nonce}'; "
            f"style-src 'nonce-{nonce}'; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
    })
