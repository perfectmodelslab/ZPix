<script lang="ts">
	import type { LassoToolProps, LassoToolEvents } from "./types";
	import { IconButton } from "@gradio/atoms";
	import { Gradio } from "@gradio/utils";
	import { onDestroy, onMount } from "svelte";
	import { find_host, type CanvasHost } from "./canvas_host";
	import LassoIcon from "./LassoIcon.svelte";
	import { LassoOverlay, OVERLAY_TAG, type Point } from "./lasso";

	const props = $props();
	const gradio = new Gradio<LassoToolEvents, LassoToolProps>(props);

	// This component renders nothing in place: its overlay goes over the
	// document displayed by the canvas, and its button in the canvas toolbar.
	const overlay = document.createElement(OVERLAY_TAG) as LassoOverlay;
	let button: HTMLElement;

	let old_value: Point[] | null = gradio.props.value ?? null;
	overlay.value = old_value;

	let host: CanvasHost | null = $state(null);
	/** Whether user selected this tool in the canvas. */
	let active = $state(false);
	let forget_host: (() => void) | null = null;

	function same_lasso(a: Point[] | null, b: Point[] | null): boolean {
		return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
	}

	/** Tell whether lasso appeared or disappeared, if so. */
	function dispatch_presence(old: Point[] | null, value: Point[] | null): void {
		if (!old && value) gradio.dispatch("drawn");
		else if (old && !value) gradio.dispatch("cleared");
	}

	function attach(canvas: CanvasHost): void {
		if (host) return;

		host = canvas;
		canvas.stage.append(overlay);
		canvas.add_tool(gradio.shared.id, button);
		overlay.area = canvas.area;
		overlay.target = canvas.image;

		const update = (): void => {
			active = canvas.tool === gradio.shared.id;
		};
		canvas.addEventListener("tool-change", update);
		update();
	}

	function toggle(): void {
		if (host) host.tool = active ? null : gradio.shared.id;
	}

	function is_text_field(target: EventTarget | null): boolean {
		return (
			target instanceof HTMLElement &&
			(target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
		);
	}

	/**
	 * L selects this tool, unless user types text with pointer away from the
	 * canvas area. Only its button deselects it.
	 */
	function on_keydown(event: KeyboardEvent): void {
		if (
			!host ||
			active ||
			gradio.shared.visible === false ||
			gradio.shared.interactive === false ||
			event.key.toLowerCase() !== "l" ||
			event.defaultPrevented ||
			event.altKey ||
			event.ctrlKey ||
			event.metaKey ||
			(is_text_field(event.target) && !host.area.matches(":hover"))
		) {
			return;
		}

		event.preventDefault();
		host.tool = gradio.shared.id;
	}

	onMount(() => {
		// Nothing stays in place, so the Gradio wrapper takes no room in layout,
		// e.g. no gap in a column.
		if (button.parentElement) button.parentElement.hidden = true;

		// Not passed back to overlay, which emitted it.
		overlay.addEventListener("lasso-change", (event) => {
			const value = (event as CustomEvent<Point[] | null>).detail;
			dispatch_presence(old_value, value);
			old_value = value;
			gradio.props.value = value;
			gradio.dispatch("input");
			gradio.dispatch("change");
		});

		const canvas_id = gradio.props.canvas_id;
		if (canvas_id !== null) forget_host = find_host(canvas_id, attach);
	});

	onDestroy(() => {
		forget_host?.();
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
		overlay.toggleAttribute(
			"disabled",
			!active || gradio.shared.interactive === false
		);
		overlay.toggleAttribute("hidden", gradio.shared.visible === false);
		overlay.toggleAttribute("static", gradio.props.marching_ants === false);
		overlay.smoothing = gradio.props.smoothing ?? 1;
		overlay.tooltips = [
			gradio.props.draw_tooltip ?? "",
			gradio.props.clear_tooltip ?? ""
		];
	});
</script>

<svelte:window onkeydown={on_keydown} />

<!-- Moved into the canvas toolbar once attached. -->
<div
	bind:this={button}
	hidden={!host || gradio.shared.visible === false}
>
	<IconButton
		Icon={LassoIcon}
		label={(active
			? gradio.props.disable_tooltip
			: gradio.props.enable_tooltip) ?? ""}
		disabled={gradio.shared.interactive === false}
		onclick={toggle}
	/>
</div>
