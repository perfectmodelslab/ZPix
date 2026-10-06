# Gradio Lasso Tool

A custom component to draw a freehand lasso over the image displayed by a `gr.Gallery`, e.g. to mask a region to edit.

```python
from gradio_lasso_tool import LassoTool, lasso_to_mask

gallery = gr.Gallery(...)
lasso = LassoTool(
    gallery=gallery,
    draw_tooltip="...",
    clear_tooltip="...",
)

# Later, e.g. in an event listener:
mask = lasso_to_mask(points, image.size)
```

Value is a list of `(x, y)` vertices in pixels of the original image, or `None` when no lasso is drawn.

The lasso persists when the gallery displays another image, scaled to its resolution if it differs.

Over the image:

- a drag draws a new lasso, which replaces the current one at once, as a line following the pointer. On release, the lasso closes from the last vertex back to the first one, then its outline marches (pass `marching_ants=False` to keep it still),
- <kbd>Esc</kbd> cancels the lasso being drawn, which brings the current one back,
- a click clears the lasso,
- a drag leaving the gallery rather drops the image onto another element that accepts drops, e.g. a prompt left of the gallery, as its URL (`text/uri-list`).

The line drawn follows the `--lasso-tool-color` CSS variable, the Gradio accent color by default. The cursor is the [Lucide](https://lucide.dev) lasso icon (ISC License).

## Development

Requires Node.js 24.

- `build.ps1 -Target grc` (at project root) builds the wheel ZPix installs from `wheels` directory. Rebuild after any component change.
- `dev.ps1` runs the hot reload demo.

On Gradio update, pin `svelte` in `frontend/package.json` to the version Gradio's frontend uses, then rebuild the wheel.
