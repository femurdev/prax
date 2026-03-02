(function () {
  const MAP_ID = "map_01";
  const GRID = 120;
  const MIN_CELL_PX = 4;
  const MAX_CELL_PX = 28;
  const DEFAULT_CELL_PX = 10;

  let socket = null;
  let mapData = null;
  let worldState = null;
  let canvas = null;
  let ctx = null;
  let currentPlayerId = null;
  let cellPx = DEFAULT_CELL_PX;
  let viewportEl = null;
  let resizeObserver = null;

  function getPlayerId() {
    if (currentPlayerId) return currentPlayerId;
    const u = window.__praxUser;
    currentPlayerId = u && (u.id != null) ? String(u.id) : "guest-" + Math.random().toString(36).slice(2, 9);
    return currentPlayerId;
  }

  function getCameraCenter() {
    if (!worldState || !worldState.players) return { x: GRID / 2 - 0.5, y: GRID / 2 - 0.5 };
    const me = worldState.players[getPlayerId()];
    if (me && me.x != null && me.y != null) return { x: me.x + 0.5, y: me.y + 0.5 };
    return { x: GRID / 2 - 0.5, y: GRID / 2 - 0.5 };
  }

  function connect() {
    if (socket) return socket;
    const origin = window.location.origin;
    socket = io(origin, { path: "/socket.io", transports: ["websocket", "polling"] });
    socket.on("connect", () => {
      socket.emit("join_game", { map_id: MAP_ID, player_id: getPlayerId() });
    });
    socket.on("state", (state) => {
      worldState = state;
      draw();
    });
    socket.on("delta", (delta) => {
      if (!worldState || delta.type !== "delta") return;
      worldState.tick = delta.tick;
      if (delta.players) {
        for (const [pid, pos] of Object.entries(delta.players)) {
          if (worldState.players[pid]) {
            worldState.players[pid].x = pos.x;
            worldState.players[pid].y = pos.y;
          }
        }
      }
      draw();
    });
    socket.on("action_queued", () => {});
    return socket;
  }

  function disconnect() {
    if (resizeObserver && viewportEl) {
      try { resizeObserver.unobserve(viewportEl); } catch (_) {}
    }
    resizeObserver = null;
    viewportEl = null;
    if (socket) {
      socket.emit("leave_game", { map_id: MAP_ID, player_id: getPlayerId() });
      socket.disconnect();
      socket = null;
    }
    currentPlayerId = null;
    worldState = null;
  }

  function resizeCanvas() {
    if (!canvas || !viewportEl) return;
    const dpr = window.devicePixelRatio || 1;
    const w = viewportEl.clientWidth;
    const h = viewportEl.clientHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    if (ctx) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    }
    draw();
  }

  function draw() {
    if (!canvas || !ctx || !mapData) return;
    const cw = viewportEl ? viewportEl.clientWidth : canvas.width;
    const ch = viewportEl ? viewportEl.clientHeight : canvas.height;
    if (cw <= 0 || ch <= 0) return;

    const w = mapData.width || GRID;
    const h = mapData.height || GRID;
    const borderEmoji = (mapData.emojis && mapData.emojis.border) || "⬛";
    const wallEmoji = (mapData.emojis && mapData.emojis.wall) || "🧱";
    const wallSet = new Set((mapData.walls || []).map((c) => c[0] + "," + c[1]));

    const cam = getCameraCenter();
    const cellsW = cw / cellPx;
    const cellsH = ch / cellPx;
    const x0 = Math.floor(cam.x - cellsW / 2);
    const y0 = Math.floor(cam.y - cellsH / 2);
    const x1 = Math.ceil(cam.x + cellsW / 2);
    const y1 = Math.ceil(cam.y + cellsH / 2);

    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, cw, ch);
    ctx.font = cellPx + "px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (let wy = y0; wy <= y1; wy++) {
      for (let wx = x0; wx <= x1; wx++) {
        const px = (wx - cam.x + cellsW / 2) * cellPx + cellPx / 2;
        const py = (wy - cam.y + cellsH / 2) * cellPx + cellPx / 2;
        const isBorder = wx < 0 || wx >= w || wy < 0 || wy >= h || wx === 0 || wx === w - 1 || wy === 0 || wy === h - 1;
        const isWall = !isBorder && wallSet.has(wx + "," + wy);
        let emoji = null;
        if (isBorder) emoji = borderEmoji;
        else if (isWall) emoji = wallEmoji;
        if (emoji) {
          ctx.fillText(emoji, px, py);
        }
      }
    }

    if (worldState && worldState.players) {
      for (const p of Object.values(worldState.players)) {
        if (p.emoji == null || p.x == null || p.y == null) continue;
        const wx = p.x + 0.5;
        const wy = p.y + 0.5;
        const px = (wx - cam.x + cellsW / 2) * cellPx + cellPx / 2;
        const py = (wy - cam.y + cellsH / 2) * cellPx + cellPx / 2;
        if (px >= -cellPx && px <= cw + cellPx && py >= -cellPx && py <= ch + cellPx) {
          ctx.fillText(p.emoji, px, py);
        }
      }
    }
  }

  function zoomIn() {
    cellPx = Math.min(MAX_CELL_PX, cellPx + 2);
    draw();
  }

  function zoomOut() {
    cellPx = Math.max(MIN_CELL_PX, cellPx - 2);
    draw();
  }

  async function start() {
    const el = document.getElementById("world-map-canvas");
    viewportEl = el && el.parentElement;
    if (!el || !viewportEl) return;
    canvas = el;
    ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (!mapData) {
      try {
        const res = await fetch("/api/maps/" + MAP_ID);
        if (!res.ok) return;
        mapData = await res.json();
      } catch (_) {
        return;
      }
    }

    resizeCanvas();
    resizeObserver = new ResizeObserver(resizeCanvas);
    resizeObserver.observe(viewportEl);

    connect();

    document.getElementById("world-map-zoom-in")?.addEventListener("click", zoomIn);
    document.getElementById("world-map-zoom-out")?.addEventListener("click", zoomOut);

    const runBtn = document.getElementById("btn-run-action");
    const editor = document.getElementById("action-code-editor");
    if (runBtn && editor) {
      runBtn.onclick = () => {
        if (!socket || !socket.connected) return;
        socket.emit("submit_action", {
          map_id: MAP_ID,
          player_id: getPlayerId(),
          action_code: editor.value || "",
        });
      };
    }
  }

  function stop() {
    disconnect();
  }

  window.praxGame = { start, stop };
})();
