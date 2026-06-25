# Agent browser for scholarly harvesting:
# Neko + Brave + a control extension (force-installed), noVNC viewer, and xdotool for
# Cloudflare. Build context is the repo root: `docker compose build` from container/.
FROM ghcr.io/m1k1o/neko/brave:latest
USER root

# Node (runs the ws-bridge) — tarball is faster than apt's full nodejs tree
RUN curl -fsSL https://nodejs.org/dist/v20.18.0/node-v20.18.0-linux-x64.tar.gz -o /tmp/node.tgz \
 && tar -xzf /tmp/node.tgz -C /opt && rm /tmp/node.tgz \
 && ln -sf /opt/node-v20.18.0-linux-x64/bin/node /usr/bin/node \
 && ln -sf /opt/node-v20.18.0-linux-x64/bin/npm /usr/bin/npm

# noVNC viewer (no-auth) + xdotool (real X11 input for Cloudflare)
RUN apt-get update && apt-get install -y --no-install-recommends \
      x11vnc novnc websockify xdotool && rm -rf /var/lib/apt/lists/*

# Control extension (drives the browser; the bridge talks to it)
RUN mkdir -p /usr/share/brave/extensions /opt/envoy
COPY container/extension/ /usr/share/brave/extensions/envoy/
RUN chown -R neko:neko /usr/share/brave/extensions

# Bridge: HTTP/WS that queues commands for the extension + serves static files
COPY container/ws-bridge.js /opt/envoy/ws-bridge.js
COPY container/bridge.conf /etc/neko/supervisord/bridge.conf
RUN cd /opt/envoy && npm init -y >/dev/null 2>&1 && npm install ws

# Browser launch flags + base managed policy
COPY container/brave.conf /etc/neko/supervisord/brave.conf
COPY container/policies.json /etc/brave/policies/managed/policies.json

# Force-install the extension via managed policy.
# Chromium/Brave >= 137 ignore --load-extension (security kill-switch); a policy
# force-install (signed .crx + local update manifest) still loads. pack-crx.sh packs
# the .crx at build, serves it from the bridge, and writes the ExtensionInstallForcelist.
COPY container/pack-crx.sh /opt/envoy/pack-crx.sh
RUN bash /opt/envoy/pack-crx.sh

# noVNC stack (x11vnc -nopw -> websockify --web). Open /vnc.html?autoconnect=true
COPY container/x11vnc.conf /etc/neko/supervisord/x11vnc.conf
COPY container/websockify.conf /etc/neko/supervisord/websockify.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/neko/supervisord.conf"]
