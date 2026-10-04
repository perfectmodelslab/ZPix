# Gradio Mask Bounding Box

A custom component to draw, move and resize a bounding box over the image displayed by a `gr.Gallery`, e.g. to mask a region to edit.

```python
from gradio_maskboundingbox import MaskBoundingBox

gallery = gr.Gallery(...)
mask_bbox = MaskBoundingBox(
    gallery=gallery,
    draw_tooltip="...",
    clear_tooltip="...",
)
```

Value is `{"x", "y", "width", "height"}` in pixels of the original image, or `None` when no bounding box is drawn.

The bounding box persists when the gallery displays another image, scaled to its resolution if it differs.

Outside the bounding box:

- a click clears the bounding box,
- a drag to the right draws a new one, which replaces the bounding box at once,
- a drag to the left draws a new one too, which replaces the bounding box on release only (meanwhile faded): leaving the gallery, it rather drops the image onto another element that accepts drops, e.g. a prompt left of the gallery, as its URL (`text/uri-list`).

Inside, a drag moves the bounding box, or resizes it from an edge or corner.

## Development

Requires Node.js 24.

- `build.ps1 -Target grc` (at project root) builds the wheel ZPix installs from `wheels` directory. Rebuild after any component change.
- `dev.ps1` runs the hot reload demo.

On Gradio update, pin `svelte` in `frontend/package.json` to the version Gradio's frontend uses, then rebuild the wheel.
