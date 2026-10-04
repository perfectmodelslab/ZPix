/**
 * Bounding box overlay, drawn over an image displayed with `object-fit: contain`.
 *
 * The overlay goes inside a positioned parent of the image and only covers
 * the image content, i.e. not the letterbox bands added by `object-fit`.
 * Bounding box coordinates are in pixels of the original image.
 */

export interface BoundingBox {
	x: number;
	y: number;
	width: number;
	height: number;
}

/** Edge or corner a bounding box is resized from, as compass directions. */
type Handle = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";

const EDGES: Handle[] = ["n", "e", "s", "w"];
const CORNERS: Handle[] = ["ne", "se", "sw", "nw"];

interface Point {
	x: number;
	y: number;
}

interface Size {
	width: number;
	height: number;
}

/** Bounding boxes smaller than this (in original image pixels) are dropped. */
const MIN_SIZE = 3;

/**
 * Pointer moves up to this (in CSS pixels) are a click's jitter, not a move.
 * No one draws a bounding box that small anyway.
 */
const MOVE_THRESHOLD = 10;

const STYLE = `
	:host {
		position: absolute;
		display: none;
		z-index: 1;
		cursor: crosshair;
		touch-action: none;
		user-select: none;
	}

	:host([hidden]) {
		display: none !important;
	}

	:host([disabled]) {
		pointer-events: none;
	}

	/* During a gesture, its cursor (set on host) stays, whatever is pointed. */
	:host([gesture]) * {
		cursor: inherit !important;
	}

	/* Dims image outside the bounding box, so region to edit stands out. */
	#shade {
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.3s;
	}

	/* Fades in and out rather than flashing. */
	:host([dimmed]) #shade {
		opacity: 1;
	}

	#hole {
		position: absolute;
		box-shadow: 0 0 0 100vmax var(--mask-bbox-dim, rgba(0, 0, 0, 0.3));
	}

	#bbox,
	#draft {
		position: absolute;
		display: none;
		box-sizing: border-box;
		border: 2px solid var(--mask-bbox-color, var(--color-accent, #f97316));
	}

	#bbox {
		cursor: move;
	}

	#draft {
		border-style: dashed;
	}

	/* Bounding box that the one user draws may replace. */
	:host([drafting]) #bbox {
		opacity: 0.5;
	}

	:host([disabled]) #bbox {
		cursor: default;
	}

	:host([disabled]) .edge,
	:host([disabled]) .corner {
		display: none;
	}

	/* Bounding box resizes from its edges and corners, wider than its border. */
	.edge,
	.corner {
		position: absolute;
	}

	.edge.n, .edge.s {
		left: 0;
		right: 0;
		height: var(--mask-bbox-edge-size, 12px);
		cursor: ns-resize;
	}

	.edge.e, .edge.w {
		top: 0;
		bottom: 0;
		width: var(--mask-bbox-edge-size, 12px);
		cursor: ew-resize;
	}

	.edge.n { top: 0; transform: translateY(-50%); }
	.edge.e { right: 0; transform: translateX(50%); }
	.edge.s { bottom: 0; transform: translateY(50%); }
	.edge.w { left: 0; transform: translateX(-50%); }

	/* Hint that the bounding box resizes. */
	.corner {
		width: var(--mask-bbox-corner-size, var(--size-2, 8px));
		height: var(--mask-bbox-corner-size, var(--size-2, 8px));
		border-radius: 50%;
		background: white;
		box-shadow: 0 0 0 1px #f7f6f6bc, 1px 1px 4px #0000001a;
	}

	/* Corner is grabbed beyond its dot, like edges beyond the border. */
	.corner::before {
		content: "";
		position: absolute;
		inset: -2px;
	}

	.corner.ne { right: 0; top: 0; transform: translate(50%, -50%); cursor: nesw-resize; }
	.corner.se { right: 0; bottom: 0; transform: translate(50%, 50%); cursor: nwse-resize; }
	.corner.sw { left: 0; bottom: 0; transform: translate(-50%, 50%); cursor: nesw-resize; }
	.corner.nw { left: 0; top: 0; transform: translate(-50%, -50%); cursor: nwse-resize; }
`;

export class BoundingBoxOverlay extends HTMLElement {
	#target: HTMLImageElement | null = null;
	/** As drawn, kept intact while browsing images. */
	#bbox: BoundingBox | null = null;
	/** Resolution of the image bounding box was drawn over. */
	#size: Size | null = null;
	#bbox_el: HTMLDivElement;
	#draft_el: HTMLDivElement;
	#hole_el: HTMLDivElement;
	/** Last emitted value, as JSON, to emit only changes. */
	#emitted = "null";

	/**
	 * Element bounding box is drawn within, e.g. the gallery: a drawing
	 * leaving it to the left is in fact a drag of image to another element.
	 */
	area: HTMLElement | null = null;

	#tooltips: [string, string] = ["", ""];

	#mode: "press" | "draw" | "draft" | "drop" | "drag" | "resize" | null =
		null;
	/** Where user pressed, in client pixels, to tell a click from a move. */
	#press: Point | null = null;
	/** Where user pressed, in original image pixels. */
	#start: Point | null = null;
	/** Bounding box as it was when user pressed. */
	#original: BoundingBox | null = null;
	/** Bounding box drawn to the left, which replaces the current one on release. */
	#draft: BoundingBox | null = null;
	#handle: Handle | null = null;
	/** Element outside overlay that pointer is over, while user drags image. */
	#drop_target: Element | null = null;
	/** Whether drop target accepts displayed image. */
	#droppable = false;
	#drag_data: DataTransfer | null = null;

	#resize_observer = new ResizeObserver(() => this.sync());
	#on_load = (): void => this.#update();

	constructor() {
		super();

		const shadow = this.attachShadow({ mode: "open" });
		const style = document.createElement("style");
		style.textContent = STYLE;

		this.#bbox_el = document.createElement("div");
		this.#bbox_el.id = "bbox";
		// Corners come last, to be grabbed over edges.
		this.#bbox_el.innerHTML = [
			...EDGES.map((h) => `<div class="edge ${h}" data-handle="${h}"></div>`),
			...CORNERS.map((h) => `<div class="corner ${h}" data-handle="${h}"></div>`)
		].join("");

		// Clicking it doesn't clear it.
		this.#bbox_el.title = "";

		this.#draft_el = document.createElement("div");
		this.#draft_el.id = "draft";

		const shade = document.createElement("div");
		shade.id = "shade";
		this.#hole_el = document.createElement("div");
		this.#hole_el.id = "hole";
		shade.append(this.#hole_el);

		shadow.append(style, shade, this.#bbox_el, this.#draft_el);

		this.addEventListener("pointerdown", (e) => this.#on_pointerdown(e));
		this.addEventListener("pointermove", (e) => this.#on_pointermove(e));
		this.addEventListener("pointerup", () => this.#on_pointerup());
		this.addEventListener("pointercancel", () => this.#on_pointercancel());

		// The overlay sits in the gallery preview button, whose click
		// shows the previous or next image: don't let our clicks reach it.
		this.addEventListener("click", (e) => e.stopPropagation());
	}

	/**
	 * Image to draw the bounding box over. Bounding box persists when another
	 * image is displayed, scaled to its resolution, so user finds it back
	 * while browsing images.
	 */
	get target(): HTMLImageElement | null {
		return this.#target;
	}

	set target(image: HTMLImageElement | null) {
		if (this.#target !== image) {
			if (this.#target) {
				this.#resize_observer.unobserve(this.#target);
				this.#target.removeEventListener("load", this.#on_load);
			}

			this.#target = image;
			this.#reset();

			if (image) {
				this.#resize_observer.observe(image);
				image.addEventListener("load", this.#on_load);
			}
		}

		this.#update();
	}

	/**
	 * Tooltips shown over the image: while no bounding box is drawn, e.g. to
	 * tell how to draw one, then outside the drawn one, e.g. to tell how to
	 * clear it.
	 */
	get tooltips(): [string, string] {
		return this.#tooltips;
	}

	set tooltips(tooltips: [string, string]) {
		this.#tooltips = tooltips;
		this.#render();
	}

	/**
	 * Bounding box in pixels of the displayed image, scaled to it.
	 * Setting it emits no event.
	 */
	get value(): BoundingBox | null {
		return this.#scaled();
	}

	set value(bbox: BoundingBox | null) {
		this.#bbox = bbox ? { ...bbox } : null;
		// Value refers to displayed image, if any.
		this.#size = natural_size(this.#target) ?? this.#size;
		this.#emitted = JSON.stringify(round(this.#scaled()));
		this.#reset();
		this.#render();
	}

	clear(): void {
		this.#bbox = null;
		this.#reset();
		this.#render();
		this.#emit();
	}

	/** Cover image content, letterbox bands excluded. */
	sync(): void {
		const image = this.#target;
		// Not offsetParent, which is null while overlay is hidden.
		const parent = this.parentElement;

		if (
			!image?.isConnected ||
			!parent ||
			!image.naturalWidth ||
			!image.naturalHeight
		) {
			this.style.display = "none";
			return;
		}

		const image_rect = image.getBoundingClientRect();
		const parent_rect = parent.getBoundingClientRect();

		// As `object-fit: contain` does: scale to fit, then center.
		const scale = Math.min(
			image_rect.width / image.naturalWidth,
			image_rect.height / image.naturalHeight
		);
		const width = image.naturalWidth * scale;
		const height = image.naturalHeight * scale;

		if (width <= 0 || height <= 0) {
			this.style.display = "none";
			return;
		}

		const left =
			image_rect.left - parent_rect.left - parent.clientLeft +
			(image_rect.width - width) / 2;
		const top =
			image_rect.top - parent_rect.top - parent.clientTop +
			(image_rect.height - height) / 2;

		this.style.display = "block";
		this.style.left = `${left}px`;
		this.style.top = `${top}px`;
		this.style.width = `${width}px`;
		this.style.height = `${height}px`;
	}

	/** Follow displayed image, which may be another one. */
	#update(): void {
		// Value set before any image was displayed refers to the first one.
		this.#size ??= natural_size(this.#target);
		this.sync();
		this.#render();
		this.#emit();
	}

	/**
	 * Bounding box scaled to displayed image, whose resolution may differ
	 * from the drawn one, so it covers the same region.
	 */
	#scaled(): BoundingBox | null {
		const bbox = this.#bbox;
		const size = natural_size(this.#target);
		if (!bbox || !size || !this.#size) return bbox;

		const scale_x = size.width / this.#size.width;
		const scale_y = size.height / this.#size.height;

		return {
			x: bbox.x * scale_x,
			y: bbox.y * scale_y,
			width: bbox.width * scale_x,
			height: bbox.height * scale_y
		};
	}

	#point_from_event(event: PointerEvent): Point {
		const image = this.#target!;
		const rect = this.getBoundingClientRect();
		const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
		const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));

		return {
			x: (x / rect.width) * image.naturalWidth,
			y: (y / rect.height) * image.naturalHeight
		};
	}

	#render(): void {
		const image = this.#target;
		const loaded = !!image?.naturalWidth && !!image.naturalHeight;
		const bbox = loaded ? this.#scaled() : null;
		const draft = loaded ? this.#draft : null;
		// Region to edit, once user releases.
		const region = draft ?? bbox;

		this.title = this.#tooltips[bbox ? 1 : 0];
		this.toggleAttribute("dimmed", !!region);
		this.toggleAttribute("drafting", !!draft);
		this.#bbox_el.style.display = bbox ? "block" : "none";
		this.#draft_el.style.display = draft ? "block" : "none";

		// Hole keeps its last place when hidden, for the dim to fade out there.
		if (region) place(this.#hole_el, region, image!);
		if (bbox) place(this.#bbox_el, bbox, image!);
		if (draft) place(this.#draft_el, draft, image!);
	}

	/** Emit value, if changed. */
	#emit(): void {
		const bbox = round(this.#scaled());
		const json = JSON.stringify(bbox);
		if (json === this.#emitted) return;

		this.#emitted = json;
		this.dispatchEvent(new CustomEvent("bbox-change", { detail: bbox }));
	}

	/**
	 * Outside the bounding box, a click clears it, and a drag draws a new one.
	 * Drag direction tells how. To the right, the new bounding box replaces
	 * the current one at once. To the left, user may as well drag displayed
	 * image to another element, e.g. a prompt left of the gallery: the new
	 * bounding box only replaces the current one on release, and leaving the
	 * area (gallery) turns the drawing into a drop.
	 *
	 * Inside, a drag moves the bounding box, or resizes it from an edge or corner.
	 */
	#on_pointerdown(event: PointerEvent): void {
		if (!this.#target || event.button !== 0) return;

		event.preventDefault();
		event.stopPropagation();

		this.#reset();

		const path = event.composedPath();
		const handle = path.find(
			(el): el is HTMLElement =>
				el instanceof HTMLElement && !!el.dataset.handle
		);

		// User edits bounding box as displayed, i.e. scaled to this image.
		const bbox = this.#scaled();
		this.#bbox = bbox;
		this.#size = natural_size(this.#target);
		this.#original = bbox;
		this.#start = this.#point_from_event(event);

		if (handle && bbox) {
			this.#mode = "resize";
			this.#handle = handle.dataset.handle as Handle;
			this.#set_cursor(getComputedStyle(handle).cursor);
		} else if (path.includes(this.#bbox_el) && bbox) {
			this.#mode = "drag";
			this.#set_cursor("move");
		} else {
			this.#mode = "press";
			this.#press = { x: event.clientX, y: event.clientY };
		}

		this.setPointerCapture(event.pointerId);
	}

	#on_pointermove(event: PointerEvent): void {
		if (!this.#target || !this.#mode) return;

		if (this.#mode === "press") {
			const dx = event.clientX - this.#press!.x;
			const dy = event.clientY - this.#press!.y;
			if (Math.hypot(dx, dy) <= MOVE_THRESHOLD) return;

			this.#mode = dx < 0 ? "draft" : "draw";
			this.#set_cursor("crosshair");
		}

		if (this.#mode === "draft" && this.#left_area(event)) {
			this.#mode = "drop";
			this.#draft = null;
			this.#render();
		}

		if (this.#mode === "drop") {
			this.#drag_over(event);
			return;
		}

		const image = this.#target;
		const point = this.#point_from_event(event);

		if (this.#mode === "draw") {
			this.#bbox = normalize(this.#start!, point);
		} else if (this.#mode === "draft") {
			this.#draft = normalize(this.#start!, point);
		} else if (this.#mode === "drag") {
			const box = this.#original!;
			this.#bbox = {
				...box,
				x: clamp(
					box.x + point.x - this.#start!.x,
					0,
					image.naturalWidth - box.width
				),
				y: clamp(
					box.y + point.y - this.#start!.y,
					0,
					image.naturalHeight - box.height
				)
			};
		} else {
			const box = this.#original!;
			const handle = this.#handle!;
			// Only dragged edges follow the pointer, others stay in place.
			const top_left = { x: box.x, y: box.y };
			const bottom_right = { x: box.x + box.width, y: box.y + box.height };
			if (handle.includes("n")) top_left.y = point.y;
			if (handle.includes("s")) bottom_right.y = point.y;
			if (handle.includes("w")) top_left.x = point.x;
			if (handle.includes("e")) bottom_right.x = point.x;
			this.#bbox = normalize(top_left, bottom_right);
		}

		this.#render();
	}

	#on_pointerup(): void {
		const mode = this.#mode;

		if (mode === "press") {
			// A mere click.
			this.clear();
		} else if (mode === "drop") {
			if (this.#droppable) {
				this.#drag_event(this.#drop_target!, "drop");
				// Dropped, so not left.
				this.#drop_target = null;
			}
			this.#reset();
		} else if (mode) {
			if (mode === "draft") this.#bbox = this.#draft;
			this.#commit();
		}
	}

	#on_pointercancel(): void {
		if (this.#mode) this.#cancel();
	}

	/** Keep bounding box as user edited it, unless it's too small. */
	#commit(): void {
		const bbox = this.#bbox;
		this.#reset();

		if (!bbox || bbox.width < MIN_SIZE || bbox.height < MIN_SIZE) {
			this.clear();
			return;
		}

		this.#render();
		this.#emit();
	}

	/** Back to bounding box as it was before user pressed. */
	#cancel(): void {
		this.#bbox = this.#original;
		this.#reset();
		this.#render();
	}

	/** Forget ongoing gesture, if any. */
	#reset(): void {
		if (this.#drop_target) this.#drag_event(this.#drop_target, "dragleave");

		this.#mode = null;
		this.#press = null;
		this.#start = null;
		this.#original = null;
		this.#draft = null;
		this.#handle = null;
		this.#drop_target = null;
		this.#droppable = false;
		this.#drag_data = null;
		this.#set_cursor(null);
	}

	/** Cursor of ongoing gesture, whatever is pointed, if any. */
	#set_cursor(cursor: string | null): void {
		this.style.cursor = cursor ?? "";
		this.toggleAttribute("gesture", !!cursor);
	}

	/** Whether pointer left the area bounding box is drawn within. */
	#left_area(event: PointerEvent): boolean {
		const rect = (this.area ?? this).getBoundingClientRect();
		return (
			event.clientX < rect.left ||
			event.clientX > rect.right ||
			event.clientY < rect.top ||
			event.clientY > rect.bottom
		);
	}

	/**
	 * Drag displayed image over the element pointer is over, outside overlay,
	 * as browser would do. Overlay can't let browser drag the image itself:
	 * it would take any drag over it, those editing the bounding box included.
	 */
	#drag_over(event: PointerEvent): void {
		const hit = document.elementFromPoint(event.clientX, event.clientY);
		const target = hit === this ? null : hit;

		if (target !== this.#drop_target) {
			if (target) this.#drag_event(target, "dragenter");
			if (this.#drop_target) this.#drag_event(this.#drop_target, "dragleave");
			this.#drop_target = target;
		}

		// Element accepts a drop by canceling dragover.
		this.#droppable = !!target && !this.#drag_event(target, "dragover");
		this.#set_cursor(this.#droppable ? "copy" : "grabbing");
	}

	/** Returns false if canceled. */
	#drag_event(target: Element, type: string): boolean {
		// Carries image URL, as browser does, e.g. Firefox.
		if (!this.#drag_data) {
			this.#drag_data = new DataTransfer();
			this.#drag_data.setData("text/uri-list", this.#target!.currentSrc);
		}

		return target.dispatchEvent(
			new DragEvent(type, {
				bubbles: true,
				cancelable: true,
				composed: true,
				dataTransfer: this.#drag_data
			})
		);
	}
}

/** Resolution of an image, once loaded. */
function natural_size(image: HTMLImageElement | null): Size | null {
	return image?.naturalWidth && image.naturalHeight
		? { width: image.naturalWidth, height: image.naturalHeight }
		: null;
}

/** Place an element over a region of image, which overlay covers. */
function place(el: HTMLElement, box: BoundingBox, image: HTMLImageElement): void {
	el.style.left = `${(box.x / image.naturalWidth) * 100}%`;
	el.style.top = `${(box.y / image.naturalHeight) * 100}%`;
	el.style.width = `${(box.width / image.naturalWidth) * 100}%`;
	el.style.height = `${(box.height / image.naturalHeight) * 100}%`;
}

function round(bbox: BoundingBox | null): BoundingBox | null {
	return (
		bbox && {
			x: Math.round(bbox.x),
			y: Math.round(bbox.y),
			width: Math.round(bbox.width),
			height: Math.round(bbox.height)
		}
	);
}

function clamp(value: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, value));
}

function normalize(a: Point, b: Point): BoundingBox {
	return {
		x: Math.min(a.x, b.x),
		y: Math.min(a.y, b.y),
		width: Math.abs(b.x - a.x),
		height: Math.abs(b.y - a.y)
	};
}

export const OVERLAY_TAG = "mask-bounding-box-overlay";

if (!customElements.get(OVERLAY_TAG)) {
	customElements.define(OVERLAY_TAG, BoundingBoxOverlay);
}
