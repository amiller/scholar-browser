#!/bin/bash
# Pack the Envoy extension into a signed .crx (headless, no GUI), serve update manifest
# from the bridge, and force-install via Brave managed policy (bypasses --load-extension kill-switch).
set -e
mkdir -p /opt/envoy/web
[ -f /opt/envoy/key.pem ] || openssl genrsa -out /opt/envoy/key.pem 2048 2>/dev/null
rm -rf /tmp/envoy-src /tmp/envoy-src.crx /tmp/packprofile
cp -r /usr/share/brave/extensions/envoy /tmp/envoy-src
timeout 90 /usr/bin/brave-browser --headless=new --no-sandbox --disable-gpu \
  --user-data-dir=/tmp/packprofile \
  --pack-extension=/tmp/envoy-src --pack-extension-key=/opt/envoy/key.pem \
  >/tmp/pack.log 2>&1 || true
if [ ! -f /tmp/envoy-src.crx ]; then echo "PACK FAILED"; tail -15 /tmp/pack.log; exit 1; fi
cp /tmp/envoy-src.crx /opt/envoy/web/envoy.crx
ID=$(openssl rsa -in /opt/envoy/key.pem -pubout -outform DER 2>/dev/null | sha256sum | head -c 32 | tr '0-9a-f' 'a-p')
cat > /opt/envoy/web/update.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
  <app appid="$ID">
    <updatecheck codebase="http://localhost:3000/envoy.crx" version="0.1.0" />
  </app>
</gupdate>
XML
cat > /etc/brave/policies/managed/policies.json <<POL
{
  "BrowserSignin": 0,
  "SyncDisabled": true,
  "DefaultNotificationsSetting": 2,
  "DefaultPopupsSetting": 2,
  "PasswordManagerEnabled": false,
  "BrowserGuestModeEnabled": false,
  "BrowserAddPersonEnabled": false,
  "ExtensionInstallForcelist": [
    "$ID;http://localhost:3000/update.xml"
  ],
  "ExtensionInstallAllowlist": ["$ID", "*"],
  "ExtensionInstallBlocklist": []
}
POL
echo "EXTID=$ID"
ls -l /opt/envoy/web/
