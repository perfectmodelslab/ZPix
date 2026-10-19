/**
 * Selection overlay, drawn over an image displayed with `object-fit: contain`.
 *
 * The overlay goes inside a positioned parent of the image and only covers
 * the image content, i.e. not the letterbox bands added by `object-fit`.
 * Selection vertices are in pixels of the original image.
 *
 * A lasso outline is drawn in segments: freehand ones, following the pointer
 * while pressed, and straight ones, from a vertex to the next click. Each lasso
 * mode draws one kind by default, and the other with Alt. A shape outline,
 * rectangle or ellipse, is dragged from a corner to the opposite one, or from
 * its center. A shape tool rather moves the selection dragged from inside.
 */

import {
	clamp,
	combine,
	constrain,
	contains,
	ellipse,
	invert,
	rectangle,
	round,
	smooth,
	translate,
	type Box,
	type Operation,
	type Point,
	type Selection,
	type Size
} from "./geometry";

export type { Point, Selection } from "./geometry";

/**
 * How an outline is drawn: "freehand" by dragging, "polygonal" by clicking
 * vertices, which straight segments join, or "rectangle" and "ellipse" by
 * dragging a box the shape fits in.
 */
export type Mode = "freehand" | "polygonal" | "rectangle" | "ellipse";

/** Whether a mode drags a shape, rather than drawing a lasso. */
function is_shape(mode: Mode): boolean {
	return mode === "rectangle" || mode === "ellipse";
}

/** Keys held during a pointer or keyboard event. */
interface Keys {
	shiftKey: boolean;
	altKey: boolean;
	ctrlKey: boolean;
	metaKey: boolean;
}

/** An outline needs this many vertices to enclose a region. */
const MIN_POINTS = 3;

/**
 * Pointer moves up to this (in CSS pixels) are a click's jitter, not a move.
 * No one draws a selection that small anyway.
 */
const MOVE_THRESHOLD = 10;

/** Vertices closer than this (in original image pixels) to the previous one are dropped. */
const MIN_SPACING = 1;

/** A click this close (in CSS pixels) to the first vertex closes the outline. */
const CLOSE_DISTANCE = 8;

/** Two clicks within this delay (in ms) and MOVE_THRESHOLD make a double-click. */
const DOUBLE_CLICK_DELAY = 500;

/** Whether on macOS, where Cmd plays the part of Ctrl. */
export const IS_MAC = /Mac|iPhone|iPad/.test(navigator.userAgent);

/** Cmd on macOS, else Ctrl: the modifier of app shortcuts. */
export function primary_key(keys: Keys): boolean {
	return IS_MAC ? keys.metaKey : keys.ctrlKey;
}

/**
 * Lasso icon from Lucide (https://lucide.dev/icons/lasso) and its polygonal
 * variant, whose hotspot is the tip of the rope, and move icon from Lucide
 * (https://lucide.dev/icons/move), whose hotspot is its center. Cursors are
 * outlined in white to stand out on dark images.
 *
 * Copyright (c) 2026 Lucide Icons and Contributors. ISC License: permission
 * to use, copy, modify, and/or distribute this software for any purpose with
 * or without fee is hereby granted, provided that the above copyright notice
 * and this permission notice appear in all copies.
 */
const ROPE_END = '<path d="M7 22a5 5 0 0 1-2-3.994"/><circle cx="5" cy="16" r="2"/>';

/** Shapes are dragged with a crosshair, whose hotspot is its center. */
const CROSSHAIR = '<path d="M12 4v16M4 12h16"/>';

/** Icon of the cursor: of a mode, or of moving the selection. */
type Icon = Mode | "move";

const ICONS: Record<Icon, string> = {
	freehand: '<path d="M3.704 14.467a10 8 0 1 1 3.115 2.375"/>' + ROPE_END,
	// Hexagon inscribed in the freehand loop, a corner on the knot.
	polygonal: '<path d="M4.35 14.11 2.3 8.2 9.1 2.3l9.7 1.9 2.9 7.6-6.8 5.9-7.93-1.36"/>' + ROPE_END,
	rectangle: CROSSHAIR,
	ellipse: CROSSHAIR,
	move:
		'<path d="M12 2v20"/><path d="m15 19-3 3-3-3"/><path d="m19 9 3 3-3 3"/>' +
		'<path d="M2 12h20"/><path d="m5 9-3 3 3 3"/><path d="m9 5 3-3 3 3"/>'
};

/** What the cursor tells a click or drag would do. */
type Sign = Operation | "close";

/** Signs at the bottom right of the icon. */
const SIGNS: Record<Sign, string> = {
	add: '<path d="M22 26h8M26 22v8"/>',
	subtract: '<path d="M22 26h8"/>',
	intersect: '<path d="M23 23l6 6M29 23l-6 6"/>',
	close: '<circle cx="26" cy="26" r="3"/>'
};

const CURSORS = new Map<string, string>();

/** Cursor of an icon, with a sign if any, which makes it 1.5 times larger. */
function icon_cursor(name: Icon, sign: Sign | null): string {
	const key = `${name} ${sign}`;
	const cached = CURSORS.get(key);
	if (cached) return cached;

	const icon = ICONS[name] + (sign ? SIGNS[sign] : "");
	// Icons are 24 units, shown 16px, or 20px for the crosshair of shapes.
	const scale = name === "rectangle" || name === "ellipse" ? 20 / 24 : 16 / 24;
	const view_size = sign ? 36 : 24;
	const size = view_size * scale;
	// Same scale with or without a sign, hence the same hotspot.
	const [x, y] = name === "freehand" || name === "polygonal" ? [7.5, 22.5] : [12, 12];
	const hotspot = `${Math.round(x * scale)} ${Math.round(y * scale)}`;
	const svg =
		`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" ` +
		`viewBox="0 0 ${view_size} ${view_size}" fill="none" ` +
		'stroke-linecap="round" stroke-linejoin="round">' +
		`<g stroke="white" stroke-width="4">${icon}</g>` +
		`<g stroke="black" stroke-width="2">${icon}</g></svg>`;
	const fallback = name === "move" ? "move" : "crosshair";
	const cursor = `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${hotspot}, ${fallback}`;

	CURSORS.set(key, cursor);
	return cursor;
}

const STYLE = `
	:host {
		position: absolute;
		display: none;
		z-index: 1;
		touch-action: none;
		user-select: none;
	}

	:host([hidden]) {
		display: none !important;
	}

	/* Cursor changes as overlay gets enabled, for browser to show it at once. */
	:host([disabled]) {
		pointer-events: none;
		cursor: auto;
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
	path {
		display: none;
		fill: none;
		stroke-width: 1px;
	}

	#draft {
		stroke: var(--select-tool-color, var(--color-accent, #f97316));
	}

	/* Marching ants: black dashes over a white line. */
	#selection {
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

export class SelectionOverlay extends HTMLElement {
	#target: HTMLImageElement | null = null;
	/** As drawn, kept intact while browsing images. */
	#selection: Selection | null = null;
	/** Resolution of the image selection was drawn over. */
	#size: Size | null = null;
	/** Last selection user cleared, which they may select back, and its resolution. */
	#deselected: { selection: Selection; size: Size | null } | null = null;
	#draft_el: SVGPolylineElement;
	#selection_el: SVGPathElement;
	#ants_el: SVGPathElement;
	/** Last emitted value, as JSON, to emit only changes. */
	#emitted = "null";

	/**
	 * Element selection is drawn within, e.g. the canvas: a drawing leaving it
	 * is in fact a drag of image to another element.
	 */
	area: HTMLElement | null = null;

	/** Element image shows in, letterbox bands included, which take clicks while drawing. Null for the parent. */
	bands: HTMLElement | null = null;

	/** Neighbors each vertex of freehand segments is averaged with on each side, to smooth the hand's jitter. */
	smoothing = 1;

	#mode: Mode = "freehand";
	#disabled = false;
	#tooltips: [string, string] = ["", ""];

	/** Pointer pressed: not moved yet, dragged, or dragging the image away. */
	#gesture: "press" | "drag" | "drop" | null = null;
	/** Whether an outline is being drawn, pointer pressed or not. */
	#drawing = false;
	/** Whether this drag started the outline, which leaving the area drops then. */
	#fresh = false;
	/** What outline being drawn does to the current selection, if not replace it. */
	#operation: Operation | null = null;
	/** Operation of the shortcut held while pointer is over overlay, if any. */
	#held: Operation | null = null;
	/** Whether pointer hovers the selection, which a shape tool moves then. */
	#over = false;
	/** Whether user moves the selection, rather than draws. */
	#moving = false;
	/** Modifiers held since the press which set the operation, so don't constrain a shape. */
	#latched = { shift: false, alt: false };
	/** Where user pressed, in client pixels, to tell a click from a move. */
	#press: Point | null = null;
	/** Where user pressed, in image pixels. */
	#press_point: Point | null = null;
	/** Selection as it was when user started drawing or moving it, back if user cancels. */
	#original: Selection | null = null;
	/** Vertices of the outline being drawn, applied to the current selection once closed. */
	#draft: Point[] | null = null;
	/** Draft length at the end of each segment, back to which Delete goes. */
	#marks: number[] = [];
	/** Whether pointer draws a freehand segment, else a straight one. */
	#freehand = false;
	/** Index of the first vertex of the freehand segment being drawn. */
	#run_start = 0;
	/** End of the straight segment being drawn, where pointer is. */
	#hover: Point | null = null;
	/** Where pointer is, in client and in image pixels, and keys held then. */
	#client: Point | null = null;
	#pointer: Point | null = null;
	#keys: Keys | null = null;
	/** Last click while drawing, to tell a double-click. */
	#last_click: { time: number; at: Point } | null = null;
	/** Element outside overlay that pointer is over, while user drags image. */
	#drop_target: Element | null = null;
	/** Whether drop target accepts displayed image. */
	#droppable = false;
	#drag_data: DataTransfer | null = null;

	#resize_observer = new ResizeObserver(() => this.#update());
	#on_load = (): void => this.#update();

	/** Tell what a drag would do, as user presses or releases a shortcut. */
	#on_shortcut_key = (event: KeyboardEvent): void => {
		// Pointer left without a pointerleave, e.g. overlay got disabled.
		if (!this.matches(":hover")) {
			this.#on_pointerleave();
			return;
		}

		// Else Firefox shows its menu bar as Alt is released.
		if (event.key === "Alt") event.preventDefault();

		this.#hold(event);
	};

	/**
	 * While user presses or draws: Escape cancels, Delete removes the last
	 * segment, and modifiers change the segment or shape being drawn. Captured
	 * before others, e.g. the canvas, which leaves fullscreen on Escape.
	 */
	#on_drawing_key = (event: KeyboardEvent): void => {
		const keydown = event.type === "keydown";

		if (keydown && event.key === "Escape") {
			event.preventDefault();
			event.stopPropagation();
			this.#cancel();
			return;
		}

		if (keydown && (event.key === "Delete" || event.key === "Backspace")) {
			if (this.#undo_segment()) {
				event.preventDefault();
				event.stopPropagation();
			}
			return;
		}

		if (!["Shift", "Alt", "Control", "Meta"].includes(event.key)) return;
		if (event.key === "Alt") event.preventDefault();

		// Released Alt, pointer up, closes straight segments of a freehand lasso.
		if (
			!keydown &&
			event.key === "Alt" &&
			this.#mode === "freehand" &&
			this.#drawing &&
			!this.#gesture &&
			!this.#freehand
		) {
			this.#commit();
			return;
		}

		if (this.#client) this.#track(this.#client, event);
	};

	/** Pointer moves anywhere while user presses or draws. */
	#on_window_pointermove = (event: PointerEvent): void => {
		this.#track([event.clientX, event.clientY], event);
	};

	/** Clicks on letterbox bands add vertices too while drawing, clamped to image. */
	#on_window_pointerdown = (event: PointerEvent): void => {
		const target = event.target as Node | null;
		const bands = this.bands ?? this.parentElement;
		if (this.#drawing && target !== this && bands?.contains(target)) {
			this.#on_pointerdown(event);
		}
	};

	constructor() {
		super();

		const shadow = this.attachShadow({ mode: "open" });
		const style = document.createElement("style");
		style.textContent = STYLE;

		const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
		// Outline being drawn goes over the selection it adds to or subtracts from.
		svg.innerHTML =
			'<path id="selection"></path>' +
			'<path id="ants"></path>' +
			'<polyline id="draft"></polyline>';
		this.#draft_el = svg.querySelector("#draft")!;
		this.#selection_el = svg.querySelector("#selection")!;
		this.#ants_el = svg.querySelector("#ants")!;

		shadow.append(style, svg);

		this.addEventListener("pointerenter", (e) => this.#on_pointerenter(e));
		this.addEventListener("pointerleave", () => this.#on_pointerleave());
		this.addEventListener("pointerdown", (e) => this.#on_pointerdown(e));
		// Only hovering: moves while user presses or draws go to the window listener.
		this.addEventListener("pointermove", (e) => this.#busy || this.#hold(e));
		this.addEventListener("pointerup", (e) => this.#on_pointerup(e));
		this.addEventListener("pointercancel", () => this.#busy && this.#cancel());
	}

	/**
	 * Image to draw the selection over. Selection persists when another image
	 * is displayed, scaled to its resolution, so user finds it back while
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

			if (this.#busy) this.#cancel();
			this.#target = image;

			if (image) {
				this.#resize_observer.observe(image);
				image.addEventListener("load", this.#on_load);
			}
		}

		this.#update();
	}

	/** How user draws. Changing it closes the outline being drawn, if any. */
	get mode(): Mode {
		return this.#mode;
	}

	set mode(mode: Mode) {
		if (mode === this.#mode) return;

		this.#finish();
		this.#mode = mode;
		this.#over = false;
		this.#update_cursor();
	}

	/** Whether user can't draw. Disabling closes the outline being drawn, if any. */
	get disabled(): boolean {
		return this.#disabled;
	}

	set disabled(disabled: boolean) {
		if (disabled === this.#disabled) return;

		this.#finish();
		this.#disabled = disabled;
		this.toggleAttribute("disabled", disabled);
		this.#update_cursor();
	}

	/**
	 * Tooltips shown over the image: while nothing is selected, e.g. to tell
	 * how to select, then once selected, e.g. to tell how to clear it.
	 */
	get tooltips(): [string, string] {
		return this.#tooltips;
	}

	set tooltips(tooltips: [string, string]) {
		this.#tooltips = tooltips;
		this.#render();
	}

	/**
	 * Selection in pixels of the displayed image, scaled to it.
	 * Setting it emits no event.
	 */
	get value(): Selection | null {
		return this.#scaled();
	}

	set value(selection: Selection | null) {
		this.#selection =
			selection && selection.map((outline) => outline.map(([x, y]): Point => [x, y]));
		// Value refers to displayed image, if any.
		this.#size = natural_size(this.#target) ?? this.#size;
		this.#emitted = JSON.stringify(round(this.#scaled()));
		this.#reset();
		this.#render();
	}

	/** Clear the selection, which `reselect` brings back. */
	clear(): void {
		if (this.#busy) this.#cancel();
		if (this.#selection) this.#deselected = { selection: this.#selection, size: this.#size };

		this.#selection = null;
		this.#reset();
		this.#render();
		this.#emit();
	}

	/** Bring back the last selection cleared, if any, in place of the current one. */
	reselect(): void {
		if (this.#busy) this.#cancel();
		if (!this.#deselected) return;

		this.#selection = this.#deselected.selection;
		this.#size = this.#deselected.size;
		this.#render();
		this.#emit();
	}

	/** Select what isn't, and only that: the whole image if nothing is. */
	invert(): void {
		if (this.#busy) this.#cancel();

		const size = natural_size(this.#target);
		if (!size) return;

		let inverted: Selection | null;
		try {
			inverted = invert(this.#scaled(), size);
		} catch (error) {
			console.warn("Select tool couldn't invert selection:", error);
			return;
		}

		if (!inverted) {
			this.clear();
			return;
		}

		this.#selection = inverted;
		this.#size = size;
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

	/** Whether user presses or draws. */
	get #busy(): boolean {
		return this.#gesture !== null || this.#drawing;
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
	 * Selection scaled to displayed image, whose resolution may differ from
	 * the drawn one, so it surrounds the same region.
	 */
	#scaled(): Selection | null {
		const selection = this.#selection;
		const size = natural_size(this.#target);
		if (!selection || !size || !this.#size) return selection;

		const scale_x = size.width / this.#size.width;
		const scale_y = size.height / this.#size.height;

		return selection.map((outline) =>
			outline.map(([x, y]): Point => [x * scale_x, y * scale_y])
		);
	}

	/** Image point at client coordinates, clamped to image. */
	#point_at([client_x, client_y]: Point): Point {
		const image = this.#target!;
		const rect = this.getBoundingClientRect();
		const x = clamp(client_x - rect.left, 0, rect.width);
		const y = clamp(client_y - rect.top, 0, rect.height);

		return [
			(x / rect.width) * image.naturalWidth,
			(y / rect.height) * image.naturalHeight
		];
	}

	/** Distance between image points, in CSS pixels. */
	#css_distance([x1, y1]: Point, [x2, y2]: Point): number {
		const image = this.#target!;
		return Math.hypot(
			((x1 - x2) * this.clientWidth) / image.naturalWidth,
			((y1 - y2) * this.clientHeight) / image.naturalHeight
		);
	}

	#render(): void {
		const image = this.#target;
		const loaded = !!natural_size(image);
		const selection = loaded ? this.#scaled() : null;
		const outline = loaded ? this.#outline() : null;

		this.title = this.#drawing ? "" : this.#tooltips[selection ? 1 : 0];

		this.#draft_el.style.display = outline ? "inline" : "none";
		// Drawn in overlay pixels, for strokes and dashes to keep their size.
		if (outline) this.#draft_el.setAttribute("points", this.#to_svg(outline, image!));

		for (const el of [this.#selection_el, this.#ants_el]) {
			el.style.display = selection ? "inline" : "none";
			if (selection) {
				el.setAttribute(
					"d",
					selection.map((outline) => `M${this.#to_svg(outline, image!)}Z`).join("")
				);
			}
		}
	}

	/**
	 * Outline being drawn, as shown: shape closed, freehand segment smoothed
	 * as on its end, since last vertices settle as next ones come, or straight
	 * segment to pointer.
	 */
	#outline(): Point[] | null {
		const draft = this.#draft;
		if (!this.#drawing || !draft?.length) return null;

		if (is_shape(this.#mode)) return [...draft, draft[0]];

		if (this.#freehand) {
			const start = this.#run_start;
			return [...draft.slice(0, start), ...smooth(draft.slice(start), this.#smoothing_radius())];
		}

		return this.#hover ? [...draft, this.#hover] : draft;
	}

	/** SVG points of vertices, in overlay pixels. */
	#to_svg(points: Point[], image: HTMLImageElement): string {
		const scale_x = this.clientWidth / image.naturalWidth;
		const scale_y = this.clientHeight / image.naturalHeight;

		return points.map(([x, y]) => `${x * scale_x},${y * scale_y}`).join(" ");
	}

	/** Emit value, if changed. */
	#emit(): void {
		const selection = round(this.#scaled());
		const json = JSON.stringify(selection);
		if (json === this.#emitted) return;

		this.#emitted = json;
		this.dispatchEvent(new CustomEvent("selection-change", { detail: selection }));
	}

	#on_pointerenter(event: PointerEvent): void {
		window.addEventListener("keydown", this.#on_shortcut_key, true);
		window.addEventListener("keyup", this.#on_shortcut_key, true);
		this.#hold(event);
	}

	#on_pointerleave(): void {
		window.removeEventListener("keydown", this.#on_shortcut_key, true);
		window.removeEventListener("keyup", this.#on_shortcut_key, true);
		this.#held = null;
		this.#over = false;
		this.#update_cursor();
	}

	/**
	 * Operation of the shortcut held, if any. None for a shape while nothing is
	 * selected: its modifiers rather constrain it.
	 */
	#shortcut(keys: Keys): Operation | null {
		return is_shape(this.#mode) && !this.#selection ? null : shortcut_operation(keys);
	}

	/** Whether pointer, at `client`, is over the selection, which a shape tool moves. */
	#over_selection(client: Point): boolean {
		if (!is_shape(this.#mode) || !this.#target) return false;

		const selection = this.#scaled();
		return !!selection && contains(selection, this.#point_at(client));
	}

	/** Tell what a click or drag would do, as pointer hovers or user presses or releases a shortcut. */
	#hold(event: KeyboardEvent | PointerEvent): void {
		const held = this.#shortcut(event);
		const over =
			event instanceof PointerEvent
				? this.#over_selection([event.clientX, event.clientY])
				: this.#over;
		if (held === this.#held && over === this.#over) return;

		this.#held = held;
		this.#over = over;
		this.#update_cursor();
	}

	/**
	 * A press, unless an outline is being drawn, prepares one, which starts
	 * as the pointer moves, or on release for a polygonal lasso. Shift held
	 * then adds the outline drawn to the current selection, Alt subtracts it,
	 * and both intersect it: for a shape, only if something is selected, else
	 * they constrain it. Else the outline replaces the current selection as it
	 * starts, or, for a shape pressed inside the selection, moves it.
	 */
	#on_pointerdown(event: PointerEvent): void {
		if (!this.#target || event.button !== 0 || this.#gesture) return;

		event.preventDefault();
		event.stopPropagation();

		const client: Point = [event.clientX, event.clientY];
		const point = this.#point_at(client);

		if (!this.#drawing) {
			this.#reset();

			// User edits selection as displayed, i.e. scaled to this image.
			this.#selection = this.#scaled();
			this.#size = natural_size(this.#target);
			this.#original = this.#selection;
			this.#operation = this.#shortcut(event);
			const operating = this.#operation !== null;
			this.#latched = { shift: operating && event.shiftKey, alt: operating && event.altKey };
			this.#moving = !operating && this.#over_selection(client);
			this.#draft = [point];
			this.#marks = [1];
			this.#listen(true);
		}

		this.#gesture = "press";
		this.#press = client;
		this.#press_point = point;
		this.setPointerCapture(event.pointerId);
		this.#track(client, event);
	}

	/**
	 * Follow pointer, at `client`, or modifiers, as user presses or draws.
	 *
	 * A freehand lasso draws freehand while dragged, and straight segments
	 * once released with Alt held: from then on, clicks with Alt held add
	 * vertices, and releasing Alt while dragging goes freehand again.
	 * A polygonal lasso draws straight segments to the pointer, and freehand
	 * while dragged with Alt held. Shift snaps a straight segment to 45°.
	 * A shape is dragged from the press to the pointer, as is the selection
	 * moved.
	 */
	#track(client: Point, keys: Keys): void {
		this.#client = client;
		this.#keys = keys;

		if (this.#gesture === "drop") {
			this.#drag_over(client);
			return;
		}

		const draft = this.#draft;
		if (!this.#target || !draft) return;

		const point = this.#point_at(client);
		const shape = is_shape(this.#mode);
		this.#pointer = point;
		let dragged_now = false;

		if (this.#gesture === "press") {
			const [x, y] = this.#press!;
			if (Math.hypot(client[0] - x, client[1] - y) > MOVE_THRESHOLD) {
				this.#gesture = "drag";
				dragged_now = true;
				if (!this.#drawing && !this.#moving) this.#begin(true);
			}
		}

		if (this.#moving) {
			if (this.#gesture === "drag") {
				const [x0, y0] = this.#press_point!;
				this.#selection = translate(this.#original!, [point[0] - x0, point[1] - y0]);
				this.#render();
			}
			this.#update_cursor();
			return;
		}

		// Before any segment was done, leaving the area drags the image.
		if (this.#gesture === "drag" && this.#fresh && this.#left_area(client)) {
			this.#to_drop();
			this.#drag_over(client);
			return;
		}

		if (this.#gesture === "drag" && !shape) {
			const freehand =
				this.#mode === "freehand" ? this.#freehand || !keys.altKey : keys.altKey;

			if (freehand && !this.#freehand) {
				this.#start_run(dragged_now ? this.#press_point! : (this.#hover ?? point));
			} else if (!freehand && this.#freehand) {
				this.#end_run();
			}
		}

		if (shape) {
			if (this.#drawing) this.#draft = this.#shape(point, keys);
		} else if (this.#freehand) {
			const [last_x, last_y] = draft[draft.length - 1];
			if (Math.hypot(point[0] - last_x, point[1] - last_y) >= MIN_SPACING) {
				draft.push(point);
			}
		} else {
			const last = draft[draft.length - 1];
			this.#hover = keys.shiftKey
				? constrain(last, point, natural_size(this.#target)!)
				: point;
		}

		this.#render();
		this.#update_cursor();
	}

	/**
	 * Rectangle or ellipse from the press to `point`, clamped to image, or no
	 * vertex if it encloses nothing. Shift makes it a square or a circle, and
	 * Alt draws it from its center, unless they set the operation at the
	 * press: then, once released and pressed again.
	 */
	#shape(point: Point, keys: Keys): Point[] {
		this.#latched.shift &&= keys.shiftKey;
		this.#latched.alt &&= keys.altKey;

		const [x0, y0] = this.#press_point!;
		let [dx, dy] = [point[0] - x0, point[1] - y0];

		if (keys.shiftKey && !this.#latched.shift) {
			const side = Math.max(Math.abs(dx), Math.abs(dy));
			dx = dx < 0 ? -side : side;
			dy = dy < 0 ? -side : side;
		}

		if (Math.abs(dx) < MIN_SPACING || Math.abs(dy) < MIN_SPACING) return [];

		const from: Point = keys.altKey && !this.#latched.alt ? [x0 - dx, y0 - dy] : [x0, y0];
		const box: Box = [from, [x0 + dx, y0 + dy]];
		const { width, height } = natural_size(this.#target)!;

		return (this.#mode === "rectangle" ? rectangle(box) : ellipse(box)).map(
			([x, y]): Point => [clamp(x, 0, width), clamp(y, 0, height)]
		);
	}

	/**
	 * Release ends a click, which ends a straight segment, or a drag, which
	 * ends a freehand one, closes a shape or moves the selection. A click on
	 * the first vertex closes the outline, as do a double-click, a click with
	 * Ctrl (Cmd on macOS) held, which adds a vertex first, and releasing a
	 * freehand lasso without Alt held.
	 */
	#on_pointerup(event: PointerEvent): void {
		const gesture = this.#gesture;
		if (!gesture) return;

		this.#gesture = null;
		this.#fresh = false;

		if (gesture === "drop") {
			if (this.#droppable) {
				this.#drag_event(this.#drop_target!, "drop");
				// Dropped, so not left.
				this.#drop_target = null;
			}
			this.#reset();
			return;
		}

		if (this.#moving && gesture === "drag") {
			this.#reset();
			this.#render();
			this.#emit();
			return;
		}

		if (!this.#drawing) {
			// A mere click starts a polygonal lasso, and clears the selection
			// otherwise, unless a shortcut is held.
			if (this.#mode === "polygonal") {
				this.#begin(false);
				this.#last_click = { time: event.timeStamp, at: this.#press! };
				this.#render();
				this.#update_cursor();
			} else if (this.#operation) {
				this.#reset();
			} else {
				this.clear();
			}
			return;
		}

		const client: Point = [event.clientX, event.clientY];

		if (is_shape(this.#mode)) {
			this.#track(client, event);
			this.#commit();
			return;
		}

		if (this.#freehand) {
			if (this.#mode === "freehand" && !event.altKey) {
				this.#commit();
				return;
			}

			this.#end_run();
			this.#track(client, event);
			return;
		}

		this.#track(client, event);

		if (gesture === "press" && this.#is_double_click(event.timeStamp, client)) {
			this.#commit();
			return;
		}

		if (this.#near_start()) {
			this.#commit();
			return;
		}

		this.#add_vertex(this.#hover!);

		if (primary_key(event) || (this.#mode === "freehand" && !event.altKey)) {
			this.#commit();
			return;
		}

		this.#last_click = gesture === "press" ? { time: event.timeStamp, at: client } : null;
		this.#render();
		this.#update_cursor();
	}

	#is_double_click(time: number, [x, y]: Point): boolean {
		const last = this.#last_click;
		return (
			!!last &&
			time - last.time <= DOUBLE_CLICK_DELAY &&
			Math.hypot(x - last.at[0], y - last.at[1]) <= MOVE_THRESHOLD
		);
	}

	/** Whether pointer is on the first vertex of a lasso outline it can close. */
	#near_start(): boolean {
		const draft = this.#draft;
		return (
			this.#drawing &&
			!is_shape(this.#mode) &&
			!this.#freehand &&
			!!draft &&
			!!this.#pointer &&
			draft.length >= MIN_POINTS &&
			this.#css_distance(draft[0], this.#pointer) <= CLOSE_DISTANCE
		);
	}

	/** Start drawing an outline, which replaces the current selection at once if no shortcut was held. */
	#begin(dragged: boolean): void {
		this.#drawing = true;
		this.#fresh = dragged;
		if (!this.#operation) this.#selection = null;

		if (this.#mode === "freehand") {
			this.#run_start = 0;
			this.#freehand = true;
		}
	}

	/** Start a freehand segment, from `point`, after a straight one to it. */
	#start_run(point: Point): void {
		this.#add_vertex(point);
		this.#run_start = this.#draft!.length - 1;
		this.#freehand = true;
		this.#hover = null;
	}

	/** End the freehand segment, smoothed. */
	#end_run(): void {
		const draft = this.#draft!;
		const start = this.#run_start;
		draft.splice(start, Infinity, ...smooth(draft.slice(start), this.#smoothing_radius()));
		this.#marks.push(draft.length);
		this.#freehand = false;
	}

	/** End a straight segment at a vertex. */
	#add_vertex(point: Point): void {
		const draft = this.#draft!;
		const [last_x, last_y] = draft[draft.length - 1];
		if (Math.hypot(point[0] - last_x, point[1] - last_y) < MIN_SPACING) return;

		draft.push(point);
		this.#marks.push(draft.length);
	}

	/** Remove the last segment of a lasso, or cancel it if none is left. */
	#undo_segment(): boolean {
		if (!this.#drawing || this.#freehand || is_shape(this.#mode)) return false;

		this.#marks.pop();
		const end = this.#marks.at(-1);

		if (end === undefined) {
			this.#cancel();
		} else {
			this.#draft!.length = end;
			this.#last_click = null;
			if (this.#client && this.#keys) this.#track(this.#client, this.#keys);
		}
		return true;
	}

	/** Close the outline being drawn, if any, else forget the press. */
	#finish(): void {
		if (this.#drawing) this.#commit();
		else if (this.#gesture) this.#cancel();
	}

	/** Close the outline from its last vertex to its first, unless it encloses nothing, and apply it. */
	#commit(): void {
		if (this.#freehand) this.#end_run();

		const draft = this.#draft;
		const operation = this.#operation;
		const selection = this.#selection;
		const original = this.#original;
		this.#reset();

		if (!operation) {
			if (!draft || draft.length < MIN_POINTS) {
				// Cleared as drawing started, yet reselectable.
				this.#selection = original;
				this.clear();
				return;
			}

			this.#selection = [draft];
		} else if (draft && draft.length >= MIN_POINTS) {
			// Adding to no selection makes one, subtracting from or intersecting it does nothing.
			if (!selection) this.#selection = operation === "add" ? [draft] : null;
			else this.#selection = combine(selection, draft, operation) ?? selection;
		}

		this.#render();
		this.#emit();
	}

	#smoothing_radius(): number {
		return Math.max(0, Math.floor(this.smoothing)) || 0;
	}

	/** Back to selection as it was before user started drawing or moving it. */
	#cancel(): void {
		if (this.#busy && this.#gesture !== "drop") this.#selection = this.#original;
		this.#reset();
		this.#render();
	}

	/** Turn the drawing into a drag of the image. */
	#to_drop(): void {
		this.#gesture = "drop";
		this.#selection = this.#original;
		this.#drawing = false;
		this.#freehand = false;
		this.#draft = null;
		this.#hover = null;
		this.#render();
	}

	/** Forget ongoing gesture and outline, if any. */
	#reset(): void {
		if (this.#drop_target) this.#drag_event(this.#drop_target, "dragleave");

		this.#listen(false);
		this.#gesture = null;
		this.#drawing = false;
		this.#fresh = false;
		this.#operation = null;
		this.#moving = false;
		this.#latched = { shift: false, alt: false };
		this.#press = null;
		this.#press_point = null;
		this.#original = null;
		this.#draft = null;
		this.#marks = [];
		this.#freehand = false;
		this.#run_start = 0;
		this.#hover = null;
		this.#client = null;
		this.#pointer = null;
		this.#keys = null;
		this.#last_click = null;
		this.#drop_target = null;
		this.#droppable = false;
		this.#drag_data = null;
		this.#update_cursor();
	}

	/** Follow keys and pointer anywhere, while user presses or draws. */
	#listen(on: boolean): void {
		const listen = (on ? window.addEventListener : window.removeEventListener).bind(window);
		listen("keydown", this.#on_drawing_key, true);
		listen("keyup", this.#on_drawing_key, true);
		listen("pointermove", this.#on_window_pointermove, true);
		listen("pointerdown", this.#on_window_pointerdown, true);
	}

	/** Cursor of ongoing drop, if any, else of what a click or drag would do. */
	#update_cursor(): void {
		let cursor = "";

		if (this.#gesture === "drop") {
			cursor = this.#droppable ? "copy" : "grabbing";
		} else if (this.#moving || (this.#over && !this.#busy && !this.#held && !this.#disabled)) {
			cursor = icon_cursor("move", null);
		} else if (!this.#disabled) {
			// Shortcut held as user started holds until the outline closes.
			const operation = this.#busy ? this.#operation : this.#held;
			cursor = icon_cursor(this.#mode, this.#near_start() ? "close" : operation);
		}

		this.style.cursor = cursor;
		// Over letterbox bands too, which take clicks while drawing.
		const bands = this.bands ?? this.parentElement;
		if (bands) bands.style.cursor = this.#drawing ? cursor : "";
	}

	/** Whether pointer left the area selection is drawn within. */
	#left_area([x, y]: Point): boolean {
		const rect = (this.area ?? this).getBoundingClientRect();
		return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom;
	}

	/**
	 * Drag displayed image over the element pointer is over, outside overlay,
	 * as browser would do. Overlay can't let browser drag the image itself:
	 * it would take any drag over it, those drawing the selection included.
	 */
	#drag_over([x, y]: Point): void {
		const hit = document.elementFromPoint(x, y);
		const target = hit === this ? null : hit;

		if (target !== this.#drop_target) {
			if (target) this.#drag_event(target, "dragenter");
			if (this.#drop_target) this.#drag_event(this.#drop_target, "dragleave");
			this.#drop_target = target;
		}

		// Element accepts a drop by canceling dragover.
		this.#droppable = !!target && !this.#drag_event(target, "dragover");
		this.#update_cursor();
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

/** Shift adds, Alt subtracts, both intersect. */
function shortcut_operation(keys: Keys): Operation | null {
	if (keys.shiftKey && keys.altKey) return "intersect";
	if (keys.shiftKey) return "add";
	if (keys.altKey) return "subtract";
	return null;
}

/** Resolution of an image, once loaded. */
function natural_size(image: HTMLImageElement | null): Size | null {
	return image?.naturalWidth && image.naturalHeight
		? { width: image.naturalWidth, height: image.naturalHeight }
		: null;
}

export const OVERLAY_TAG = "select-tool-overlay";

if (!customElements.get(OVERLAY_TAG)) {
	customElements.define(OVERLAY_TAG, SelectionOverlay);
}
