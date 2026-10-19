/** Selection geometry, in pixels of the original image. */

import polygon_clipping from "polygon-clipping";

/** `[x, y]`, as Python passes a vertex. */
export type Point = [number, number];

/**
 * Outlines of the selected regions. A point is selected if it lies inside an
 * odd number of them, so an outline inside another one is a hole.
 */
export type Selection = Point[][];

/** What an outline drawn with a shortcut held does to the current selection. */
export type Operation = "add" | "subtract" | "intersect";

export interface Size {
	width: number;
	height: number;
}

/** Opposite corners of a box, in any order. */
export type Box = [Point, Point];

/** Max distance (in image pixels) between an ellipse and the polygon approximating it. */
const ELLIPSE_TOLERANCE = 0.25;

/**
 * Points with each one averaged with `radius` neighbors on each side, fewer
 * near the ends, which stay put: averaging across the gap a lasso closes
 * would pull them inward, and a freehand run between straight segments must
 * still meet them.
 */
export function smooth(points: Point[], radius: number): Point[] {
	const count = points.length;
	if (radius === 0) return points;

	return points.map((_point, i): Point => {
		const reach = Math.min(radius, i, count - 1 - i);
		let [x, y] = [0, 0];

		for (let j = i - reach; j <= i + reach; j++) {
			x += points[j][0];
			y += points[j][1];
		}

		const span = 2 * reach + 1;
		return [x / span, y / span];
	});
}

/**
 * End of a segment from `start` towards `point`, at a multiple of 45°, stopped
 * at the edges of an image of `size`.
 */
export function constrain(start: Point, point: Point, size: Size): Point {
	const [x0, y0] = start;
	const [dx, dy] = [point[0] - x0, point[1] - y0];
	const step = Math.PI / 4;
	const angle = Math.round(Math.atan2(dy, dx) / step) * step;
	// Exact 0 on axes, for the segment not to drift off them.
	const ux = Math.round(Math.cos(angle) * 1e9) / 1e9;
	const uy = Math.round(Math.sin(angle) * 1e9) / 1e9;

	// Pointer projected on that direction, within 22.5° of it, so ahead.
	let length = dx * ux + dy * uy;
	if (ux > 0) length = Math.min(length, (size.width - x0) / ux);
	if (ux < 0) length = Math.min(length, -x0 / ux);
	if (uy > 0) length = Math.min(length, (size.height - y0) / uy);
	if (uy < 0) length = Math.min(length, -y0 / uy);
	length = Math.max(0, length);

	return [x0 + ux * length, y0 + uy * length];
}

/** Vertices of the rectangle a box bounds. */
export function rectangle([[x0, y0], [x1, y1]]: Box): Point[] {
	return [
		[x0, y0],
		[x1, y0],
		[x1, y1],
		[x0, y1]
	];
}

/** Vertices of the ellipse a box bounds, as many as needed to be within ELLIPSE_TOLERANCE of it. */
export function ellipse([[x0, y0], [x1, y1]]: Box): Point[] {
	const [cx, cy] = [(x0 + x1) / 2, (y0 + y1) / 2];
	const [rx, ry] = [Math.abs(x1 - x0) / 2, Math.abs(y1 - y0) / 2];
	// Chord angle whose sagitta on the largest radius is the tolerance.
	const step = 2 * Math.acos(1 - Math.min(1, ELLIPSE_TOLERANCE / Math.max(rx, ry)));
	const count = Math.max(8, Math.ceil((2 * Math.PI) / step));

	return Array.from({ length: count }, (_, i): Point => {
		const angle = (2 * Math.PI * i) / count;
		return [cx + rx * Math.cos(angle), cy + ry * Math.sin(angle)];
	});
}

/** Region a selection covers: exclusive or of outlines selects what lies inside an odd number of them. */
function region(selection: Selection): polygon_clipping.MultiPolygon {
	const [first, ...others] = selection.map((ring): polygon_clipping.Polygon => [ring]);
	return polygon_clipping.xor(first, ...others);
}

/** Outlines of a region, each region apart and each hole as one, or null if empty. */
function outlines(region: polygon_clipping.MultiPolygon): Selection | null {
	// Rings repeat their first vertex last.
	const selection = region.flatMap((polygon) =>
		polygon.map((ring) => ring.slice(0, -1).map(([x, y]): Point => [x, y]))
	);

	return selection.length ? selection : null;
}

const OPERATIONS = {
	add: polygon_clipping.union,
	subtract: polygon_clipping.difference,
	intersect: polygon_clipping.intersection
} satisfies Record<Operation, unknown>;

/**
 * Selection with the region an outline encloses added, subtracted or
 * intersected, or null if nothing is left or if polygon-clipping fails.
 */
export function combine(
	selection: Selection,
	outline: Point[],
	operation: Operation
): Selection | null {
	try {
		return outlines(OPERATIONS[operation](region(selection), [outline]));
	} catch (error) {
		console.warn("Select tool couldn't combine selections:", error);
		return null;
	}
}

/**
 * Selection of what another one doesn't select within an image of `size`,
 * the whole image if no selection, or null if nothing is left.
 *
 * Throws if polygon-clipping fails.
 */
export function invert(selection: Selection | null, size: Size): Selection | null {
	const frame: Point[] = [
		[0, 0],
		[size.width, 0],
		[size.width, size.height],
		[0, size.height]
	];

	return selection
		? outlines(polygon_clipping.difference([frame], region(selection)))
		: [frame];
}

/** Whether a point is selected, i.e. inside an odd number of outlines. */
export function contains(selection: Selection, [x, y]: Point): boolean {
	let inside = false;

	for (const outline of selection) {
		// Each edge crossing a ray from the point to the right toggles it.
		for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
			const [xi, yi] = outline[i];
			const [xj, yj] = outline[j];
			if (yi > y !== yj > y && x < xi + ((y - yi) * (xj - xi)) / (yj - yi)) {
				inside = !inside;
			}
		}
	}

	return inside;
}

/** Selection moved by `[dx, dy]`. */
export function translate(selection: Selection, [dx, dy]: Point): Selection {
	return selection.map((outline) => outline.map(([x, y]): Point => [x + dx, y + dy]));
}

export function round(selection: Selection | null): Selection | null {
	return (
		selection &&
		selection.map((outline) => outline.map(([x, y]): Point => [Math.round(x), Math.round(y)]))
	);
}

export function clamp(value: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, value));
}
