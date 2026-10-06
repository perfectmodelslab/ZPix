/**
 * Freehand lasso overlay, drawn over an image displayed with `object-fit: contain`.
 *
 * The overlay goes inside a positioned parent of the image and only covers
 * the image content, i.e. not the letterbox bands added by `object-fit`.
 * Lasso vertices are in pixels of the original image.
 */

/** `[x, y]`, as Python passes a vertex. */
export type Point = [number, number];

interface Size {
	width: number;
	height: number;
}

/** A lasso needs this many vertices to enclose a region. */
const MIN_POINTS = 3;

/**
 * Pointer moves up to this (in CSS pixels) are a click's jitter, not a move.
 * No one draws a lasso that small anyway.
 */
const MOVE_THRESHOLD = 10;

/** Vertices closer than this (in original image pixels) to the previous one are dropped. */
const MIN_SPACING = 1;

/**
 * Lasso icon from Lucide (https://lucide.dev/icons/lasso), outlined in white
 * to stand out on dark images. Its hotspot is the tip of the rope.
 *
 * Copyright (c) 2026 Lucide Icons and Contributors. ISC License: permission
 * to use, copy, modify, and/or distribute this software for any purpose with
 * or without fee is hereby granted, provided that the above copyright notice
 * and this permission notice appear in all copies.
 */
const LASSO_ICON =
	'<path d="M3.704 14.467a10 8 0 1 1 3.115 2.375"/>' +
	'<path d="M7 22a5 5 0 0 1-2-3.994"/>' +
	'<circle cx="5" cy="16" r="2"/>';

const LASSO_SVG =
	'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" ' +
	'viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">' +
	`<g stroke="white" stroke-width="4">${LASSO_ICON}</g>` +
	`<g stroke="black" stroke-width="2">${LASSO_ICON}</g></svg>`;

const LASSO_CURSOR =
	`url("data:image/svg+xml,${encodeURIComponent(LASSO_SVG)}") 5 15, crosshair`;

const STYLE = `
	:host {
		position: absolute;
		display: none;
		z-index: 1;
		cursor: ${LASSO_CURSOR};
		touch-action: none;
		user-select: none;
	}

	:host([hidden]) {
		display: none !important;
	}

	:host([disabled]) {
		pointer-events: none;
	}

	svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		overflow: visible;
		pointer-events: none;
	}

	polyline,
	polygon {
		display: none;
		fill: none;
		stroke-width: 1px;
	}

	#draft {
		stroke: var(--lasso-tool-color, var(--color-accent, #f97316));
	}

	/* Marching ants: black dashes over a white line. */
	#lasso {
		stroke: white;
	}

	#ants {
		stroke: black;
		stroke-dasharray: 4 4;
		animation: march 0.6s linear infinite;
	}

	:host([static]) #ants {
		animation: none;
	}

	@keyframes march {
		to {
			stroke-dashoffset: -8;
		}
	}
`;

export class LassoOverlay extends HTMLElement {
	#target: HTMLImageElement | null = null;
	/** As drawn, kept intact while browsing images. */
	#lasso: Point[] | null = null;
	/** Resolution of the image lasso was drawn over. */
	#size: Size | null = null;
	#draft_el: SVGPolylineElement;
	#lasso_el: SVGPolygonElement;
	#ants_el: SVGPolygonElement;
	/** Last emitted value, as JSON, to emit only changes. */
	#emitted = "null";

	/**
	 * Element lasso is drawn within, e.g. the gallery: a drawing leaving it
	 * is in fact a drag of image to another element.
	 */
	area: HTMLElement | null = null;

	#tooltips: [string, string] = ["", ""];

	#mode: "press" | "draw" | "drop" | null = null;
	/** Where user pressed, in client pixels, to tell a click from a move. */
	#press: Point | null = null;
	/** Lasso as it was when user pressed, back if user cancels. */
	#original: Point[] | null = null;
	/** Lasso being drawn, which replaces the current one on release. */
	#draft: Point[] | null = null;
	/** Element outside overlay that pointer is over, while user drags image. */
	#drop_target: Element | null = null;
	/** Whether drop target accepts displayed image. */
	#droppable = false;
	#drag_data: DataTransfer | null = null;

	#resize_observer = new ResizeObserver(() => this.#update());
	#on_load = (): void => this.#update();

	/** Escape cancels the lasso being drawn, and only that. */
	#on_keydown = (event: KeyboardEvent): void => {
		if (event.key !== "Escape") return;

		event.preventDefault();
		event.stopPropagation();
		this.#cancel();
	};

	constructor() {
		super();

		const shadow = this.attachShadow({ mode: "open" });
		const style = document.createElement("style");
		style.textContent = STYLE;

		const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
		svg.innerHTML =
			'<polyline id="draft"></polyline>' +
			'<polygon id="lasso"></polygon>' +
			'<polygon id="ants"></polygon>';
		this.#draft_el = svg.querySelector("#draft")!;
		this.#lasso_el = svg.querySelector("#lasso")!;
		this.#ants_el = svg.querySelector("#ants")!;

		shadow.append(style, svg);

		this.addEventListener("pointerdown", (e) => this.#on_pointerdown(e));
		this.addEventListener("pointermove", (e) => this.#on_pointermove(e));
		this.addEventListener("pointerup", () => this.#on_pointerup());
		this.addEventListener("pointercancel", () => this.#on_pointercancel());

		// The overlay sits in the gallery preview button, whose click
		// shows the previous or next image: don't let our clicks reach it.
		this.addEventListener("click", (e) => e.stopPropagation());
	}

	/**
	 * Image to draw the lasso over. Lasso persists when another image is
	 * displayed, scaled to its resolution, so user finds it back while
	 * browsing images.
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
	 * Tooltips shown over the image: while no lasso is drawn, e.g. to tell
	 * how to draw one, then once drawn, e.g. to tell how to clear it.
	 */
	get tooltips(): [string, string] {
		return this.#tooltips;
	}

	set tooltips(tooltips: [string, string]) {
		this.#tooltips = tooltips;
		this.#render();
	}

	/**
	 * Lasso in pixels of the displayed image, scaled to it.
	 * Setting it emits no event.
	 */
	get value(): Point[] | null {
		return this.#scaled();
	}

	set value(lasso: Point[] | null) {
		this.#lasso = lasso && lasso.map(([x, y]): Point => [x, y]);
		// Value refers to displayed image, if any.
		this.#size = natural_size(this.#target) ?? this.#size;
		this.#emitted = JSON.stringify(round(this.#scaled()));
		this.#reset();
		this.#render();
	}

	clear(): void {
		this.#lasso = null;
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

	/** Follow displayed image, which may be another one or resized. */
	#update(): void {
		// Value set before any image was displayed refers to the first one.
		this.#size ??= natural_size(this.#target);
		this.sync();
		this.#render();
		this.#emit();
	}

	/**
	 * Lasso scaled to displayed image, whose resolution may differ from the
	 * drawn one, so it surrounds the same region.
	 */
	#scaled(): Point[] | null {
		const lasso = this.#lasso;
		const size = natural_size(this.#target);
		if (!lasso || !size || !this.#size) return lasso;

		const scale_x = size.width / this.#size.width;
		const scale_y = size.height / this.#size.height;

		return lasso.map(([x, y]): Point => [x * scale_x, y * scale_y]);
	}

	#point_from_event(event: PointerEvent): Point {
		const image = this.#target!;
		const rect = this.getBoundingClientRect();
		const x = clamp(event.clientX - rect.left, 0, rect.width);
		const y = clamp(event.clientY - rect.top, 0, rect.height);

		return [
			(x / rect.width) * image.naturalWidth,
			(y / rect.height) * image.naturalHeight
		];
	}

	#render(): void {
		const image = this.#target;
		const loaded = !!natural_size(image);
		const lasso = loaded ? this.#scaled() : null;
		const draft = loaded && this.#mode === "draw" ? this.#draft : null;

		this.title = this.#tooltips[lasso ? 1 : 0];

		for (const [el, points] of [
			[this.#draft_el, draft],
			[this.#lasso_el, lasso],
			[this.#ants_el, lasso]
		] as const) {
			el.style.display = points ? "inline" : "none";
			// Drawn in overlay pixels, for strokes and dashes to keep their size.
			if (points) el.setAttribute("points", this.#to_svg(points, image!));
		}
	}

	/** SVG points of vertices, in overlay pixels. */
	#to_svg(points: Point[], image: HTMLImageElement): string {
		const scale_x = this.clientWidth / image.naturalWidth;
		const scale_y = this.clientHeight / image.naturalHeight;

		return points.map(([x, y]) => `${x * scale_x},${y * scale_y}`).join(" ");
	}

	/** Emit value, if changed. */
	#emit(): void {
		const lasso = round(this.#scaled());
		const json = JSON.stringify(lasso);
		if (json === this.#emitted) return;

		this.#emitted = json;
		this.dispatchEvent(new CustomEvent("lasso-change", { detail: lasso }));
	}

	/**
	 * A click clears the lasso, and a drag draws a new one, which replaces
	 * the current one at once and closes on release. User may as well drag
	 * displayed image to another element, e.g. a prompt left of the gallery:
	 * leaving the area (gallery) turns the drawing into a drop.
	 */
	#on_pointerdown(event: PointerEvent): void {
		if (!this.#target || event.button !== 0) return;

		event.preventDefault();
		event.stopPropagation();

		this.#reset();

		// User replaces lasso as displayed, i.e. scaled to this image.
		this.#lasso = this.#scaled();
		this.#size = natural_size(this.#target);
		this.#original = this.#lasso;
		this.#mode = "press";
		this.#press = [event.clientX, event.clientY];
		this.#draft = [this.#point_from_event(event)];

		this.setPointerCapture(event.pointerId);
		// Captured before the gallery, which leaves preview on Escape.
		window.addEventListener("keydown", this.#on_keydown, true);
	}

	#on_pointermove(event: PointerEvent): void {
		if (!this.#target || !this.#mode) return;

		if (this.#mode === "press") {
			const [x, y] = this.#press!;
			if (Math.hypot(event.clientX - x, event.clientY - y) <= MOVE_THRESHOLD) {
				return;
			}

			this.#mode = "draw";
			this.#lasso = null;
		}

		if (this.#mode === "draw" && this.#left_area(event)) {
			this.#mode = "drop";
			this.#lasso = this.#original;
			this.#draft = null;
			this.#render();
		}

		if (this.#mode === "drop") {
			this.#drag_over(event);
			return;
		}

		const point = this.#point_from_event(event);
		const draft = this.#draft!;
		const [last_x, last_y] = draft[draft.length - 1];
		if (Math.hypot(point[0] - last_x, point[1] - last_y) < MIN_SPACING) return;

		draft.push(point);
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
		} else if (mode === "draw") {
			this.#commit();
		}
	}

	#on_pointercancel(): void {
		if (this.#mode) this.#cancel();
	}

	/** Close lasso as user drew it, unless it encloses nothing. */
	#commit(): void {
		const draft = this.#draft;
		this.#reset();

		if (!draft || draft.length < MIN_POINTS) {
			this.clear();
			return;
		}

		this.#lasso = draft;
		this.#render();
		this.#emit();
	}

	/** Back to lasso as it was before user pressed. */
	#cancel(): void {
		this.#lasso = this.#original;
		this.#reset();
		this.#render();
	}

	/** Forget ongoing gesture, if any. */
	#reset(): void {
		if (this.#drop_target) this.#drag_event(this.#drop_target, "dragleave");

		window.removeEventListener("keydown", this.#on_keydown, true);
		this.#mode = null;
		this.#press = null;
		this.#original = null;
		this.#draft = null;
		this.#drop_target = null;
		this.#droppable = false;
		this.#drag_data = null;
		this.#set_cursor(null);
	}

	/** Cursor of ongoing gesture, if any, in place of the lasso. */
	#set_cursor(cursor: string | null): void {
		this.style.cursor = cursor ?? "";
	}

	/** Whether pointer left the area lasso is drawn within. */
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
	 * it would take any drag over it, those drawing the lasso included.
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

function round(lasso: Point[] | null): Point[] | null {
	return lasso && lasso.map(([x, y]): Point => [Math.round(x), Math.round(y)]);
}

function clamp(value: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, value));
}

export const OVERLAY_TAG = "lasso-tool-overlay";

if (!customElements.get(OVERLAY_TAG)) {
	customElements.define(OVERLAY_TAG, LassoOverlay);
}
