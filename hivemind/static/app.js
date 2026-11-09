let csrfToken = null;
let lastFeedIds = null;
let avatarBase = "";

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[character]));

function headerActivity(milliseconds = 1400) {
  window.HiveMindTopBar?.activity(milliseconds);
}

function setHeaderState(state) {
  window.HiveMindTopBar?.setState(state);
}

function expires(iso) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Denver", hour: "numeric", minute: "2-digit",
    month: "short", day: "numeric", timeZoneName: "short",
  }).format(new Date(iso));
}

// Rendered by HiveMind's own RoboHash (k8s/robohash/), so no third party sees
// the request. The explicit .png keeps the generated hash stable regardless of
// how the server treats a missing extension. set1 is the classic robot set.
function avatar(seed) {
  return `${avatarBase}/${encodeURIComponent(seed)}.png?set=set1&size=80x80`;
}

// If the self-hosted instance is unreachable we show a local glyph rather than
// reaching for the public service: the privacy claim stays true in every case.
// An HTML error page delivered into an <img> also fails to decode and lands
// here, so a misrouted request degrades the same way an outage does.
function avatarFailed(img) {
  const glyph = document.createElement("div");
  glyph.className = "avatar-fallback";
  glyph.textContent = "\u{1F916}";
  glyph.setAttribute("role", "img");
  glyph.setAttribute("aria-label", "Robot avatar unavailable");
  img.replaceWith(glyph);
}
window.avatarFailed = avatarFailed;

function render(rows) {
  const feed = $("#feed");
  feed.innerHTML = rows.length ? rows.map((report) => `
    <article class="report">
      <img src="${avatar(report.avatar_seed)}" alt="Robot avatar"
        width="48" height="48" loading="lazy" onerror="avatarFailed(this)">
      <div>
        <p class="meta"><span class="tag ${escapeHtml(report.category)}">${escapeHtml(report.category)}</span> · attendee report</p>
        <p class="content">${escapeHtml(report.content)}</p>
        ${report.location ? `<p class="location">📍 ${escapeHtml(report.location)}</p>` : ""}
        <p class="expires">Expires ${expires(report.expires_at)}</p>
      </div>
    </article>`).join("") : "<p class=\"empty\">No active reports yet. Be the first to share what you’re seeing.</p>";
}

async function responseData(response) {
  try {
    return await response.json();
  } catch {
    return {detail: "Service is temporarily unavailable."};
  }
}

async function loadReports() {
  const category = $("#filter").value;
  const response = await fetch(`/api/reports?category=${encodeURIComponent(category)}`);
  const data = await responseData(response);
  if (!response.ok) throw new Error(data.detail || "Could not refresh reports");

  const nextIds = new Set(data.reports.map((report) => report.id));
  if (lastFeedIds) {
    const newCount = [...nextIds].filter((id) => !lastFeedIds.has(id)).length;
    if (newCount) {
      $("#feed-status").textContent = `${newCount} new report${newCount === 1 ? "" : "s"} available.`;
      headerActivity(1600);
    }
  }
  lastFeedIds = nextIds;
  render(data.reports);
}

async function bootstrap() {
  const response = await fetch("/api/session/bootstrap", {method: "POST"});
  const data = await responseData(response);
  if (!response.ok) throw new Error(data.detail || "Could not start browser session");
  if (data.csrf_token) sessionStorage.setItem("hivemind_csrf", data.csrf_token);
  csrfToken = data.csrf_token || sessionStorage.getItem("hivemind_csrf");
  avatarBase = (data.avatar_base_url || "").replace(/\/$/, "");
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await bootstrap();
    await loadReports();
  } catch (error) {
    $("#feed-status").textContent = error.message;
  }

  setInterval(() => loadReports().catch(() => {
    $("#feed-status").textContent = "Waiting to reconnect…";
  }), window.HIVEMIND_POLL_SECONDS * 1000);

  $("#filter").addEventListener("change", () => {
    lastFeedIds = null;
    loadReports();
  });
  document.querySelectorAll('input[name="expiry"]').forEach((input) => input.addEventListener("change", () => {
    $("#custom-expiry").hidden = document.querySelector('input[name="expiry"]:checked').value !== "custom";
  }));
  $("#category").addEventListener("change", (event) => {
    if (event.target.value === "coffee") document.querySelector('input[value="15m"]').checked = true;
  });
  $("#report-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const choice = document.querySelector('input[name="expiry"]:checked').value;
    const custom = $("#custom-expiry").value;
    const payload = {
      content: $("#content").value,
      location: $("#location").value || null,
      category: $("#category").value,
      expiration: choice,
      custom_expires_at: custom ? `${custom}:00` : null,
    };
    const status = $("#form-status");
    status.textContent = "Posting…";
    setHeaderState("active");
    try {
      const response = await fetch("/api/reports", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken || ""},
        body: JSON.stringify(payload),
      });
      const data = await responseData(response);
      if (!response.ok) {
        status.textContent = data.detail || "Could not post update.";
        setHeaderState("idle");
        return;
      }
      event.target.reset();
      status.textContent = "Update posted.";
      headerActivity(1600);
      await loadReports();
    } catch {
      status.textContent = "Could not post update.";
      setHeaderState("idle");
    }
  });
});
