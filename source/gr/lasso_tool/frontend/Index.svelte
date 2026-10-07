<svelte:options accessors={true} />

<script lang="ts">
	import type { LassoToolProps, LassoToolEvents } from "./types";
	import { Gradio } from "@gradio/utils";
	import { onDestroy, onMount } from "svelte";
	import { LassoOverlay, OVERLAY_TAG, type Point } from "./lasso";

	const props = $props();
	const gradio = new Gradio<LassoToolEvents, LassoToolProps>(props);

	// This component renders nothing in place: its overlay goes
	// into the gallery, over the displayed (preview) image.
	const overlay = document.createElement(OVERLAY_TAG) as LassoOverlay;

	let old_value: Point[] | null = gradio.props.value ?? null;
	overlay.value = old_value;

	let observer: MutationObserver | null = null;

	function same_lasso(a: Point[] | null, b: Point[] | null): boolean {
		return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
	}

	/** Tell whether lasso appeared or disappeared, if so. */
	function dispatch_presence(old: Point[] | null, value: Point[] | null): void {
		if (!old && value) gradio.dispatch("drawn");
		else if (old && !value) gradio.dispatch("cleared");
	}

	/** Attach overlay to the image displayed by gallery, if any. */
	function attach(gallery: HTMLElement): void {
		const image = gallery.querySelector<HTMLImageElement>(
			'.media-button img[data-testid="detailed-image"]'
		);

		if (!image) {
			overlay.target = null;
			overlay.remove();
			return;
		}

		const parent = image.parentElement!;
		if (overlay.parentElement !== parent) parent.append(overlay);

		overlay.area = gallery;
		overlay.target = image;
	}

	/** Watch gallery for displayed image changes, once it's in the DOM. */
	function watch(): void {
		const elem_id = gradio.props.gallery_elem_id;
		const gallery = elem_id ? document.getElementById(elem_id) : null;

		observer?.disconnect();

		if (!gallery) {
			if (!elem_id) return;
			observer = new MutationObserver(watch);
			observer.observe(document.body, { childList: true, subtree: true });
			return;
		}

		observer = new MutationObserver(() => attach(gallery));
		observer.observe(gallery, {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ["src"]
		});
		attach(gallery);
	}

	onMount(() => {
		// Not passed back to overlay, which emitted it.
		overlay.addEventListener("lasso-change", (event) => {
			const value = (event as CustomEvent<Point[] | null>).detail;
			dispatch_presence(old_value, value);
			old_value = value;
			gradio.props.value = value;
			gradio.dispatch("input");
			gradio.dispatch("change");
		});

		watch();
	});

	onDestroy(() => {
		observer?.disconnect();
		overlay.target = null;
		overlay.remove();
	});

	// Value set by an event.
	$effect(() => {
		const value = gradio.props.value ?? null;
		if (!same_lasso(value, old_value)) {
			dispatch_presence(old_value, value);
			old_value = value;
			overlay.value = value;
			gradio.dispatch("change");
		}
	});

	$effect(() => {
		overlay.toggleAttribute("disabled", gradio.shared.interactive === false);
		overlay.toggleAttribute("hidden", gradio.shared.visible === false);
		overlay.toggleAttribute("static", gradio.props.marching_ants === false);
		overlay.smoothing = gradio.props.smoothing ?? 1;
		overlay.tooltips = [
			gradio.props.draw_tooltip ?? "",
			gradio.props.clear_tooltip ?? ""
		];
	});
</script>

<style>
	/* Overlay is positioned against the image parent. */
	:global(:has(> lasso-tool-overlay)) {
		position: relative;
	}
</style>
