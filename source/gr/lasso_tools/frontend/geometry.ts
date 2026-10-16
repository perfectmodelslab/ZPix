/** Lasso geometry, in pixels of the original image. */

import polygon_clipping from "polygon-clipping";

/** `[x, y]`, as Python passes a vertex. */
export type Point = [number, number];

/**
 * Outlines of the selected regions. A point is selected if it lies inside an
 * odd number of them, so an outline inside another one is a hole.
 */
export type Lasso = Point[][];

/** What a lasso drawn with a shortcut held does to the current one. */
export type Operation = "add" | "subtract" | "intersect";

export interface Size {
	width: number;
	height: number;
}

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

/** Region a lasso selects: exclusive or of outlines selects what lies inside an odd number of them. */
function region(lasso: Lasso): polygon_clipping.MultiPolygon {
	const [first, ...others] = lasso.map((ring): polygon_clipping.Polygon => [ring]);
	return polygon_clipping.xor(first, ...others);
}

/** Outlines of a region, each region apart and each hole as one, or null if empty. */
function outlines(region: polygon_clipping.MultiPolygon): Lasso | null {
	// Rings repeat their first vertex last.
	const lasso = region.flatMap((polygon) =>
		polygon.map((ring) => ring.slice(0, -1).map(([x, y]): Point => [x, y]))
	);

	return lasso.length ? lasso : null;
}

const OPERATIONS = {
	add: polygon_clipping.union,
	subtract: polygon_clipping.difference,
	intersect: polygon_clipping.intersection
} satisfies Record<Operation, unknown>;

/**
 * Lasso with the region an outline encloses added, subtracted or intersected,
 * or null if nothing is left or if polygon-clipping fails.
 */
export function combine(lasso: Lasso, outline: Point[], operation: Operation): Lasso | null {
	try {
		return outlines(OPERATIONS[operation](region(lasso), [outline]));
	} catch (error) {
		console.warn("Lasso tool couldn't combine lassos:", error);
		return null;
	}
}

/**
 * Lasso selecting what another one doesn't within an image of `size`, the
 * whole image if no lasso, or null if nothing is left.
 *
 * Throws if polygon-clipping fails.
 */
export function invert(lasso: Lasso | null, size: Size): Lasso | null {
	const frame: Point[] = [
		[0, 0],
		[size.width, 0],
		[size.width, size.height],
		[0, size.height]
	];

	return lasso ? outlines(polygon_clipping.difference([frame], region(lasso))) : [frame];
}

export function round(lasso: Lasso | null): Lasso | null {
	return (
		lasso &&
		lasso.map((outline) => outline.map(([x, y]): Point => [Math.round(x), Math.round(y)]))
	);
}

export function clamp(value: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, value));
}
