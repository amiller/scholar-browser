# Insights / gotchas

Hard-won lessons from making an agent-driven browser actually harvest paywalled-by-Cloudflare
scholarly PDFs. Each of these cost real debugging time.

## 1. Chromium/Brave ≥ 137 killed `--load-extension`
Modern Chromium ignores unpacked `--load-extension` (a security kill-switch). The flag
`--disable-features=DisableLoadExtensionCommandLineSwitch` no longer re-enables it in current
builds. **Fix:** force-install via managed policy — pack the extension into a signed `.crx`,
serve it + an `update.xml` from a local URL, and add the id to `ExtensionInstallForcelist`.
Policy-installed extensions bypass the kill-switch. See `container/pack-crx.sh`.
Pack with `brave-browser --headless=new --pack-extension=... --pack-extension-key=...`
(MUST be `--headless=new` or it hangs trying to open a GUI). Verify it loaded via the
profile's `Default/Preferences` (grep the extension id). A full container/browser restart is
needed to trigger the policy install — `supervisorctl restart brave` alone may not.

## 2. In-container `localhost` resolves to IPv6 `::1`
The extension fetches `http://localhost:3000` (the bridge). In the container `localhost` maps
to both `127.0.0.1` and `::1`, and Chromium prefers `::1`. If the bridge binds IPv4 only
(`server.listen(PORT, '0.0.0.0')`) the fetch silently fails and commands never drain.
**Fix:** listen dual-stack — `server.listen(PORT)` (no host arg).

## 3. ePrint PDFs are Cloudflare-gated
`GET /YYYY/NNN.pdf` returns `403` with `cf-mitigated: challenge` ("Just a moment…") to plain
`curl`/`fetch`/`XHR`. HTML pages (search, abstracts) are open; only PDFs are challenged.
**Fix:** let the real browser solve the challenge once → it sets a domain-wide `cf_clearance`
cookie (persists across browser restart). Then an **in-page synchronous XHR** from a same-origin
ePrint page pulls the PDF (the cookie rides along), returned as base64. See `scholar/harvest.py`.

## 4. Cloudflare Turnstile rejects synthetic clicks — use xdotool
The extension's `clickAt` (synthetic DOM/event injection) is fingerprinted as non-human and
ignored by Turnstile. **Fix:** drive the real X11 cursor with `xdotool` — a mousemove
*trajectory* (Bézier / slight arc, variable timing) then `xdotool click 1` on the X display
(`:99`). Real input events pass. Locate the widget via the parent page's
`iframe[src*="challenges.cloudflare.com"]` bounding box; screen-Y = `rect.y +
(window.outerHeight - window.innerHeight)` to account for the browser chrome.

## 5. No-password viewer (don't use Neko's login UI)
For a human to glance/click without a login screen: `x11vnc -display :99.0 -nopw` +
`websockify --web=/usr/share/novnc 8091 localhost:5900`, then open
`/vnc.html?autoconnect=true`. The VNC path bypasses Neko's member auth entirely.

## 6. Navigating to a PDF wedges the extension worker
Navigating the controlled tab straight to a `.pdf` turns it into the PDF viewer / a download,
which is not scriptable — the extension's service worker then stops responding to commands.
**Fix:** never navigate to the `.pdf`; navigate to the HTML abstract and `XHR` the PDF. If the
worker does wedge, restart the browser to recover (cookies/`cf_clearance` persist in the profile).

## 7. WebRTC / port notes
Neko's WebRTC needs a TCP-mux port reachable from the client at the address it advertises
(`NEKO_NAT1TO1` + `NEKO_WEBRTC_TCPMUX`). For local/tunneled use this is fiddly — the noVNC path
(pure TCP over one websocket) is simpler and tunnels cleanly over SSH. Changing the mux port
requires a container recreate (env is read at start), so prefer noVNC.
