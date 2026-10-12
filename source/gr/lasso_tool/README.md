# Gradio Lasso Tool

A custom component to draw a freehand lasso over the document displayed by a [Canvas](../canvas/README.md), which hosts it as a tool, e.g. to mask a region to edit.

```python
from gradio_canvas import Canvas
from gradio_lasso_tool import LassoTool, lasso_to_mask

lasso = LassoTool(
    enable_tooltip="Enable lasso",
    disable_tooltip="Disable lasso",
    draw_tooltip="...",
    clear_tooltip="...",
)
canvas = Canvas(tools=[lasso])

# Later, e.g. in an event listener:
mask = lasso_to_mask(points, image.size)
```

Value is a list of `(x, y)` vertices in pixels of the base layer image, or `None` when no lasso is drawn.

The lasso button, with `enable_tooltip` as tooltip (`disable_tooltip` while selected), goes to the canvas toolbar. User draws only while the tool is selected there, and `interactive` is not False.

The lasso persists when the canvas displays another document, scaled to its resolution if it differs.

Over the image:

- a drag draws a new lasso, which replaces the current one at once, as a line following the pointer. On release, the lasso closes from the last vertex back to the first one, then its outline marches (pass `marching_ants=False` to keep it still). Each vertex is averaged with its neighbor on each side, which smooths the jitter of the hand as user draws (pass `smoothing=0` to keep the lasso as drawn, or more neighbors to smooth it more),
- a drag with <kbd>Shift</kbd> held rather adds the region it encloses to the lasso, and with <kbd>Alt</kbd> held, subtracts it. The cursor shows a plus or minus sign while these are held. If that makes several regions, e.g. when subtracting cuts the lasso in two, the largest one is kept, and holes are filled. The lasso stays as is if nothing is left,
- <kbd>Esc</kbd> cancels the lasso being drawn, which brings the current one back,
- a click clears the lasso, unless <kbd>Shift</kbd> or <kbd>Alt</kbd> is held,
- a drag leaving the canvas rather drops the image onto another element that accepts drops, e.g. a prompt left of the canvas, as its URL (`text/uri-list`).

The line drawn follows the `--lasso-tool-color` CSS variable, the Gradio accent color by default. The cursor and the button icon are the [Lucide](https://lucide.dev) lasso icon (ISC License). Lassos are added and subtracted with [polygon-clipping](https://github.com/mfogel/polygon-clipping) (MIT License). Their notices are in `NOTICE.txt`, which the wheel includes.

## Development

Requires Node.js 24.

- `build.ps1 -Target grc` (at project root) builds the wheel ZPix installs from `wheels` directory. Rebuild after any component change.
- `dev.ps1` runs the hot reload demo.

On Gradio update, pin `svelte` in `frontend/package.json` to the version Gradio's frontend uses, then rebuild the wheel.
