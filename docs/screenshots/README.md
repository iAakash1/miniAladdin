# Screenshots

**This directory is intentionally empty.**

Screenshot capture could not be performed in the environment this repository
was developed in:

- headless Chrome hangs rather than exiting, producing no file
- `screencapture` returns *"could not create image from display"* — the process
  lacks macOS screen-recording permission
- AppleScript cannot reach the browser window from this context
- the embedded browser can render and inspect pages, but returns images to the
  session rather than to disk

The production UI at [mini-aladding.vercel.app](https://mini-aladding.vercel.app)
is live and the panels documented in the README render there. What has *not*
happened is a verified visual inspection of production, so no screenshot is
committed rather than committing a mockup or a local capture labelled as
production.

To populate this directory on a machine with screen-recording permission:

```bash
# with a signed-in Chrome profile
chrome --headless=new --user-data-dir=<profile> --window-size=1280,900 \
       --screenshot=docs/screenshots/01-company-overview.png \
       https://mini-aladding.vercel.app/company/AAPL
```

Record for each capture: filename, route, company used, feature demonstrated,
whether data was live, providers visible, and capture date.
