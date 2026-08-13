"""Dark styling for the barfi graph canvas (blocks, minimap, zoom controls).

barfi's flow editor is a React Flow canvas rendered in a Streamlit iframe. It
hardcodes the light color mode and exposes no theme option, and Streamlit page
CSS can't reach inside the iframe — so the nodes, minimap and zoom controls
render on white and are hard to read.

The only thing that works is overriding the component's *own* CSS (which lives
inside the iframe, shipped in the barfi package). :func:`ensure_dark_canvas`
replaces a delimited dark-mode block in that asset — idempotent, updates in place
when the CSS below changes, and re-applies after a barfi reinstall. Call it once
at startup.
"""

from __future__ import annotations

import pathlib

_START = "/* FAERS-dark-canvas START */"
_END = "/* FAERS-dark-canvas END */"

_DARK_CSS = f"""
{_START}
/* barfi styles nodes with shadcn design tokens (hsl(var(--token))). Override
   them to a dark palette so node bodies, text, inputs and dropdowns go dark. */
:root{{
  --background:0 0% 8%;
  --foreground:0 0% 80%;
  --card:0 0% 16%;
  --card-foreground:0 0% 80%;
  --popover:0 0% 12%;
  --popover-foreground:0 0% 84%;
  --muted:0 0% 20%;
  --muted-foreground:0 0% 68%;
  --border:0 0% 32%;
  --input:0 0% 32%;
  --secondary:0 0% 22%;
  --secondary-foreground:0 0% 86%;
  --accent:0 0% 24%;
  --accent-foreground:0 0% 88%;
}}

/* Bolder grey text inside the node blocks. */
.react-flow__node,.react-flow__node *{{font-weight:600 !important;color:#b8b8b8 !important;}}

/* Canvas + edges */
.react-flow{{background:#141414 !important;}}
.react-flow__edge-path{{stroke:#8a8a8a !important;}}
.react-flow__connection-path{{stroke:#8ab4f8 !important;}}

/* Sockets */
.react-flow__handle{{background:#8ab4f8 !important;border:1px solid #8ab4f8 !important;}}

/* Minimap */
.react-flow__minimap{{background-color:#1e1e1e !important;}}
.react-flow__minimap-mask{{fill:rgba(0,0,0,.55) !important;}}
.react-flow__minimap-node{{fill:#5a5a5a !important;stroke:none !important;}}

/* Zoom controls */
.react-flow__controls{{box-shadow:0 0 0 1px #444 !important;}}
.react-flow__controls-button{{background:#2b2b2b !important;border-bottom:1px solid #444 !important;}}
.react-flow__controls-button:hover{{background:#3a3a3a !important;}}
.react-flow__controls-button svg,.react-flow__controls-button path{{fill:#e0e0e0 !important;}}
{_END}
"""


def ensure_dark_canvas() -> None:
    """Ensure barfi's flow CSS carries the current dark-canvas block."""
    try:
        import barfi

        assets = (
            pathlib.Path(barfi.__file__).parent
            / "flow"
            / "streamlit"
            / "static"
            / "assets"
        )
        for css in assets.glob("*.css"):
            text = css.read_text(encoding="utf-8", errors="ignore")
            # Drop any previously-applied block (matched loosely so older
            # formats are cleaned too — our block is always appended last).
            idx = text.find("/* FAERS-dark-canvas")
            base = (text[:idx] if idx != -1 else text).rstrip()
            new_text = base + "\n" + _DARK_CSS
            if new_text != text:
                css.write_text(new_text, encoding="utf-8")
    except Exception:  # noqa: BLE001 - purely cosmetic, never break startup
        pass
