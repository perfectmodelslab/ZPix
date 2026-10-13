"""Image discard helpers."""

from collections.abc import Callable
from pathlib import Path

from gradio_canvas import CanvasValue

from source.py.custom_logger import logger


def discard_image(
    output_dir: Path,
    t: Callable[[str], str],
    canvas: CanvasValue,
) -> CanvasValue:
    """Remove the displayed image from canvas. If it was generated, rather
    than imported, also move its file to the "Discarded" output subfolder.

    Args:
        output_dir: The folder where generated images are saved.
        t: Translation function.
        canvas: Canvas documents, the displayed one is removed from.
    """
    doc = canvas.doc

    if doc and not doc.layers[0].imported:
        try:
            source_file = doc.layers[0].source_file

            # Source file comes back from browser: only trust output folder.
            if not source_file or not source_file.resolve().is_relative_to(
                output_dir.resolve()
            ):
                raise ValueError(f"{source_file} isn't in output folder")

            discarded_dir = output_dir / t("Discarded")
            discarded_dir.mkdir(parents=True, exist_ok=True)

            source_file.move_into(discarded_dir)
        except Exception as error:  # noqa: BLE001
            # Maybe image file is gone, or outside output folder.
            logger.warning(f"Can't move image file to discarded ones: {error}")

    return canvas.delete()
