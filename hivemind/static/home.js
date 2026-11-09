let csrfToken = null;
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[character]));
const sourceAnchor = (id) => `source-${encodeURIComponent(id)}`;
function mt(iso) { return new Intl.DateTimeFormat("en-US", {timeZone:"America/Denver",hour:"numeric",minute:"2-digit",month:"short",day:"numeric",timeZoneName:"short"}).format(new Date(iso)); }
async function data(response) { try { return await response.json(); } catch { return {detail:"Service is temporarily unavailable."}; } }
async function bootstrap() { const response=await fetch("/api/session/bootstrap",{method:"POST"}), result=await data(response); if(!response.ok) throw new Error(result.detail || "Could not start browser session"); csrfToken=result.csrf_token; sessionStorage.setItem("hivemind_csrf",csrfToken); }
function official(row) { return `<article id="${sourceAnchor(`official:${row.id}`)}" class="report"><div><p class="meta">OFFICIAL EVENT</p><p class="content"><a href="${escapeHtml(row.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(row.title)}</a></p><p class="location">${escapeHtml(row.location)} · ${mt(row.starts_at)}–${mt(row.ends_at)}</p>${row.speaker_names?.length ? `<p class="location">${escapeHtml(row.speaker_names.join(", "))}</p>` : ""}</div></article>`; }
function report(row) { return `<article id="${sourceAnchor(`report:${row.id}`)}" class="report"><div><p class="meta">${row.starts_at && new Date(row.starts_at)>new Date() ? "SCHEDULED REPORT" : "ATTENDEE OBSERVATION"}</p><p class="content">${escapeHtml(row.content)}</p>${row.location ? `<p class="location">📍 ${escapeHtml(row.location)}</p>` : ""}${row.starts_at ? `<p class="location">Starts ${mt(row.starts_at)}</p>` : ""}<p class="expires">Expires ${mt(row.expires_at)}</p></div></article>`; }
function renderSummary(summary, generatedAt, windowMinutes) {
  const section = $("#generated-summary");
  if (!summary?.bullets?.length) { section.hidden = true; return; }
  $("#summary-generated-at").textContent = `Generated ${mt(generatedAt)} for the next ${windowMinutes} minutes.`;
  $("#summary-bullets").innerHTML = summary.bullets.map((bullet) => `<li>${escapeHtml(bullet.text)} ${bullet.source_ids.map((id) => `<a href="#${sourceAnchor(id)}">[source]</a>`).join(" ")}</li>`).join("");
  section.hidden = false;
}
document.addEventListener("DOMContentLoaded", async () => {
  const button=$("#summarize"), windowSelect=$("#window"), status=$("#summary-status");
  try { await bootstrap(); } catch (error) { status.textContent=error.message; button.disabled=true; }
  windowSelect.addEventListener("change", () => { button.textContent=`Summarize opportunities in the next ${windowSelect.value} minutes`; });
  button.addEventListener("click", async () => {
    button.disabled=true; status.textContent="Finding current opportunities…"; window.HiveMindTopBar?.setState("active");
    const response=await fetch("/api/opportunities/summary", {method:"POST", headers:{"Content-Type":"application/json","X-CSRF-Token":csrfToken||""}, body:JSON.stringify({window_minutes:Number(windowSelect.value)})}), result=await data(response);
    button.disabled=false; window.HiveMindTopBar?.setState("idle");
    if(!response.ok) { status.textContent=result.detail||"Could not load opportunities."; return; }
    $("#opportunities").hidden=false;
    $("#official-events").innerHTML=result.official_events.length ? result.official_events.map(official).join("") : '<p class="empty">No official events overlap this window.</p>';
    $("#attendee-reports").innerHTML=result.attendee_reports.length ? result.attendee_reports.map(report).join("") : '<p class="empty">No active attendee opportunities overlap this window.</p>';
    $("#freshness").textContent=result.schedule_freshness ? `Official schedule refreshed ${mt(result.schedule_freshness)}.` : "Official schedule has not been imported yet.";
    $("#selection-note").hidden=!result.selection_limited;
    renderSummary(result.summary, result.generated_at, result.window_minutes);
    status.textContent=result.generation_message || (result.generation_status === "cached" ? "Cached opportunity brief loaded." : "Opportunities loaded.");
  });
});
