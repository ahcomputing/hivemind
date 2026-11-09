# HiveMind top-bar UI assets

Brain in a jar, wired to a circuit board, with a hamburger menu on the right.
Two animation states: **idle** (soft bubbling, the odd spark) and **active**
(heavy bubbling, pulsing brain, continuous charge along the traces).

`templates/index.html` includes the bar, and `static/app.js` already drives it:
`headerActivity(1600)` when a poll finds new reports and after a successful
post, `setHeaderState("active")` held while a submit is in flight.

If `index.html` gets rewritten from elsewhere and the bar disappears, put the
hooks back with:

```bash
python3 tools/ui/wire_topbar.py          # idempotent
python3 tools/ui/wire_topbar.py --check  # exits non-zero if the hooks are gone
```

## Look at it

```bash
cd hivemind && python3 -m http.server 8777
# then open http://127.0.0.1:8777/static/ui/demo.html
```

The demo page is the real bar plus state toggles and a resizable narrow frame.

## What ships

Inline SVG, animated in CSS: `topbar.css`, `topbar.js`, `topbar-art.html`,
and the Jinja partial `templates/_topbar.html`. About 20 KB, no image requests,
crisp at any zoom, re-themes from CSS custom properties.

Pre-rendered sprite strips were built and compared, then dropped: 2.8 MB of PNG,
a fixed 636 px width, and a re-theme would mean re-rendering every frame. The
renderer still exists behind `build_assets.py --sprites` because the frame
machinery is handy for stills.

## Wiring (already done in `templates/index.html`)

For reference, this is what was added:

In `<head>`:

```html
<link rel="stylesheet" href="/static/ui/topbar.css">
```

First thing in `<body>`:

```html
{% include "_topbar.html" %}
```

Before `</body>`:

```html
<script src="/static/ui/topbar.js" defer></script>
<script src="/static/app.js" defer></script>
```

## Driving the animation

`window.HiveMindTopBar`:

- `activity(ms)` — go active, drop back to idle after `ms` (default 1400).
  Call this when a poll returns new reports, or when a post succeeds.
- `setState("idle" | "active")` — hold a state, e.g. around a long request.
- `getState()`
- `setMotion(bool)` / `getMotion()` — the user-facing animation toggle,
  persisted in `localStorage` under `hivemind.motion`.
- `init(root)` — re-wire after injecting markup; it never double-binds.

`setState()` cancels any fallback a previous `activity()` call scheduled, so a
hold taken across a slow request is not cut short by an earlier poll's timer.

Example:

```js
const res = await fetch("/api/reports");
if (res.ok) window.HiveMindTopBar.activity(1600);
```

## Accessibility

- The animated art is decorative and hidden from assistive technology; report
  and form status are announced by their own live regions instead.
- `prefers-reduced-motion: reduce` freezes every loop, and the menu carries a
  user toggle that overrides the OS setting either way.
- Nothing flashes faster than about 1 Hz.
- Menu: `aria-expanded`, `aria-controls`, Escape or focus-away to close,
  up/down arrows to move between items, click-outside to dismiss, 48 px touch
  target.

## Changing the art

Edit `tools/ui/brainjar.py` — it is the single source for both options — then:

```bash
python3 tools/ui/build_assets.py
```

`static/ui/topbar-art.html` and `templates/_topbar_art.html` are generated.
Do not hand-edit them.
