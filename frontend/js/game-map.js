(function () {
  const MAP_ID = "map_01";
  const CELL_PX = 8;
  const GRID = 120;

  let socket = null;
  let mapData = null;
  let worldState = null;
  let canvas = null;
  let ctx = null;
  let rafId = null;
  let currentPlayerId = null;

  function getPlayerId() {
    if (currentPlayerId) return currentPlayerId;
    const u = window.__praxUser;
    currentPlayerId = u && (u.id != null) ? String(u.id) : "guest-" + Math.random().toString(36).slice(2, 9);
    return currentPlayerId;
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
    if (socket) {
      socket.emit("leave_game", { map_id: MAP_ID, player_id: getPlayerId() });
      socket.disconnect();
      socket = null;
    }
    currentPlayerId = null;
    worldState = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  function draw() {
    if (!canvas || !ctx || !mapData) return;
    const w = mapData.width || GRID;
    const h = mapData.height || GRID;
    const borderEmoji = (mapData.emojis && mapData.emojis.border) || "⬛";
    const wallEmoji = (mapData.emojis && mapData.emojis.wall) || "🧱";
    const wallSet = new Set((mapData.walls || []).map((c) => c[0] + "," + c[1]));

    canvas.width = w * CELL_PX;
    canvas.height = h * CELL_PX;
    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = CELL_PX + "px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const isBorder = x === 0 || x === w - 1 || y === 0 || y === h - 1;
        const isWall = wallSet.has(x + "," + y);
        let emoji = null;
        if (isBorder) emoji = borderEmoji;
        else if (isWall) emoji = wallEmoji;
        if (emoji) {
          ctx.fillText(emoji, (x + 0.5) * CELL_PX, (y + 0.5) * CELL_PX);
        }
      }
    }

    if (worldState && worldState.players) {
      for (const p of Object.values(worldState.players)) {
        if (p.emoji != null && p.x != null && p.y != null) {
          ctx.fillText(p.emoji, (p.x + 0.5) * CELL_PX, (p.y + 0.5) * CELL_PX);
        }
      }
    }
  }

  async function start() {
    const el = document.getElementById("world-map-canvas");
    if (!el) return;
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

    connect();
    draw();

    const runBtn = document.getElementById("btn-run-action");
    const editor = document.getElementById("action-code-editor");
    if (runBtn && editor) {
      runBtn.onclick = () => {
        if (!socket || !socket.connected) return;
        const actionCode = editor.value || "";
        socket.emit("submit_action", {
          map_id: MAP_ID,
          player_id: getPlayerId(),
          action_code: actionCode,
        });
      };
    }
  }

  function stop() {
    disconnect();
  }

  window.praxGame = { start, stop };
})();
