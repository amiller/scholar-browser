// Minimal control extension for scholarly harvesting.
// Polls the local bridge for commands, runs them in the active tab, posts results back.
// Tools: navigate, evaluate, screenshot. No CDP, no automation flags.
const BRIDGE = "http://localhost:3000";

async function activeTabId() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t && t.id;
}

async function run(cmd) {
  const tabId = cmd.tabId || (await activeTabId());
  switch (cmd.tool) {
    case "navigate":
      await chrome.tabs.update(tabId, { url: cmd.args[0] });
      await new Promise((res) => {
        const cb = (id, info) => {
          if (id === tabId && info.status === "complete") {
            chrome.tabs.onUpdated.removeListener(cb);
            res();
          }
        };
        chrome.tabs.onUpdated.addListener(cb);
        setTimeout(() => { chrome.tabs.onUpdated.removeListener(cb); res(); }, 20000);
      });
      return { success: true };
    case "evaluate": {
      const r = await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: (code) => { try { return eval(code); } catch (e) { return { __evalError: String(e) }; } },
        args: [cmd.args[0]],
      });
      return r[0] && r[0].result;
    }
    case "screenshot":
      return await chrome.tabs.captureVisibleTab({ format: "png" });
    default:
      throw new Error("unknown tool: " + cmd.tool);
  }
}

async function poll() {
  try {
    const cmds = await (await fetch(`${BRIDGE}/api/commands`)).json();
    for (const cmd of cmds) {
      let success = true, result, error = "";
      try { result = await run(cmd); } catch (e) { success = false; error = String(e); }
      await fetch(`${BRIDGE}/api/responses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: cmd.id, success, result, error }),
      });
    }
  } catch (_) { /* bridge not ready; retry next tick */ }
}

// Keep the MV3 service worker alive and polling.
let looping = false;
async function loop() {
  if (looping) return;
  looping = true;
  const end = Date.now() + 25000;
  while (Date.now() < end) {
    await poll();
    await new Promise((r) => setTimeout(r, 200));
  }
  looping = false;
  setTimeout(loop, 0);
}
chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => loop());
chrome.runtime.onInstalled.addListener(() => loop());
chrome.runtime.onStartup.addListener(() => loop());
loop();
