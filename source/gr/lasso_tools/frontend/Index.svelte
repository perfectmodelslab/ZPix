<script lang="ts">
	import type { LassoToolProps, LassoToolEvents } from "./types";
	import { IconButton } from "@gradio/atoms";
	import { Gradio } from "@gradio/utils";
	import { onDestroy, onMount } from "svelte";
	import { find_host, type CanvasHost } from "./canvas_host";
	import { LassoGroup, type LassoTool } from "./group";
	import LassoIcon from "./LassoIcon.svelte";
	import type { Lasso } from "./lasso";
	import PolygonalLassoIcon from "./PolygonalLassoIcon.svelte";

	const props = $props();
	const gradio = new Gradio<LassoToolEvents, LassoToolProps>(props);

	// This component renders nothing in place: the lasso goes over the
	// document displayed by the canvas, on the overlay its lasso tools share,
	// and the tool button in the canvas toolbar.
	let button: HTMLElement;

	let old_value: Lasso | null = gradio.props.value ?? null;

	let host: CanvasHost | null = $state(null);
	let group: LassoGroup | null = null;
	/** Whether user selected this tool in the canvas. */
	let active = $state(false);
	let forget_host: (() => void) | null = null;

	const tool: LassoTool = {
		id: gradio.shared.id,
		state: {
			mode: "freehand",
			visible: true,
			interactive: true,
			marching_ants: true,
			smoothing: 1,
			tooltips: ["", ""]
		},
		on_change(value, input) {
			if (same_lasso(value, old_value)) return;

			dispatch_presence(old_value, value);
			old_value = value;
			gradio.props.value = value;
			if (input) gradio.dispatch("input");
			gradio.dispatch("change");
		}
	};

	function same_lasso(a: Lasso | null, b: Lasso | null): boolean {
		return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
	}

	/** Tell whether lasso appeared or disappeared, if so. */
	function dispatch_presence(old: Lasso | null, value: Lasso | null): void {
		if (!old && value) gradio.dispatch("drawn");
		else if (old && !value) gradio.dispatch("cleared");
	}

	function attach(canvas: CanvasHost): void {
		if (host) return;

		host = canvas;
		canvas.add_tool(gradio.shared.id, button);
		group = LassoGroup.of(canvas);
		group.join(tool, old_value);

		const update = (): void => {
			active = canvas.tool === gradio.shared.id;
		};
		canvas.addEventListener("tool-change", update);
		update();
	}

	function toggle(): void {
		if (host) host.tool = active ? null : gradio.shared.id;
	}

	onMount(() => {
		// Nothing stays in place, so the Gradio wrapper takes no room in layout,
		// e.g. no gap in a column.
		if (button.parentElement) button.parentElement.hidden = true;

		const canvas_id = gradio.props.canvas_id;
		if (canvas_id !== null) forget_host = find_host(canvas_id, attach);
	});

	onDestroy(() => {
		forget_host?.();
		group?.leave(gradio.shared.id);
	});

	// Value set by an event: the other lasso tools of the canvas follow.
	$effect(() => {
		const value = gradio.props.value ?? null;
		if (!same_lasso(value, old_value)) {
			dispatch_presence(old_value, value);
			old_value = value;
			group?.set_value(gradio.shared.id, value);
			gradio.dispatch("change");
		}
	});

	$effect(() => {
		tool.state = {
			mode: gradio.props.polygonal ? "polygonal" : "freehand",
			visible: gradio.shared.visible !== false,
			interactive: gradio.shared.interactive !== false,
			marching_ants: gradio.props.marching_ants !== false,
			smoothing: gradio.props.smoothing ?? 1,
			tooltips: [gradio.props.draw_tooltip ?? "", gradio.props.clear_tooltip ?? ""]
		};
		// Reading `host` applies the state again once attached.
		if (host) group?.refresh();
	});
</script>

<!-- Moved into the canvas toolbar once attached. -->
<div
	bind:this={button}
	hidden={!host || gradio.shared.visible === false}
>
	<IconButton
		Icon={gradio.props.polygonal ? PolygonalLassoIcon : LassoIcon}
		label={(active
			? gradio.props.disable_tooltip
			: gradio.props.enable_tooltip) ?? ""}
		disabled={gradio.shared.interactive === false}
		onclick={toggle}
	/>
</div>
