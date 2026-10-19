<script lang="ts">
	import type { SelectToolProps, SelectToolEvents } from "./types";
	import { IconButton } from "@gradio/atoms";
	import { Gradio } from "@gradio/utils";
	import { onDestroy, onMount } from "svelte";
	import { find_host, type CanvasHost } from "./canvas_host";
	import EllipseSelectIcon from "./EllipseSelectIcon.svelte";
	import { SelectionGroup, type SelectTool } from "./group";
	import LassoIcon from "./LassoIcon.svelte";
	import PolygonalLassoIcon from "./PolygonalLassoIcon.svelte";
	import RectangleSelectIcon from "./RectangleSelectIcon.svelte";
	import type { Selection } from "./selection";

	const ICONS = {
		freehand: LassoIcon,
		polygonal: PolygonalLassoIcon,
		rectangle: RectangleSelectIcon,
		ellipse: EllipseSelectIcon
	};

	const props = $props();
	const gradio = new Gradio<SelectToolEvents, SelectToolProps>(props);

	// This component renders nothing in place: the selection goes over the
	// document displayed by the canvas, on the overlay its select tools share,
	// and the tool button in the canvas toolbar.
	let button: HTMLElement;

	let old_value: Selection | null = gradio.props.value ?? null;

	let host: CanvasHost | null = $state(null);
	let group: SelectionGroup | null = null;
	/** Whether user selected this tool in the canvas. */
	let active = $state(false);
	let forget_host: (() => void) | null = null;

	const tool: SelectTool = {
		id: gradio.shared.id,
		state: {
			mode: gradio.props.mode,
			visible: true,
			interactive: true,
			marching_ants: true,
			smoothing: 1,
			tooltips: ["", ""]
		},
		on_change(value, input) {
			if (same_selection(value, old_value)) return;

			dispatch_presence(old_value, value);
			old_value = value;
			gradio.props.value = value;
			if (input) gradio.dispatch("input");
			gradio.dispatch("change");
		}
	};

	function same_selection(a: Selection | null, b: Selection | null): boolean {
		return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
	}

	/** Tell whether selection appeared or disappeared, if so. */
	function dispatch_presence(old: Selection | null, value: Selection | null): void {
		if (!old && value) gradio.dispatch("drawn");
		else if (old && !value) gradio.dispatch("cleared");
	}

	function attach(canvas: CanvasHost): void {
		if (host) return;

		host = canvas;
		canvas.add_tool(gradio.shared.id, button);
		group = SelectionGroup.of(canvas);
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

	// Value set by an event: the other select tools of the canvas follow.
	$effect(() => {
		const value = gradio.props.value ?? null;
		if (!same_selection(value, old_value)) {
			dispatch_presence(old_value, value);
			old_value = value;
			group?.set_value(gradio.shared.id, value);
			gradio.dispatch("change");
		}
	});

	$effect(() => {
		tool.state = {
			mode: gradio.props.mode,
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
		Icon={ICONS[gradio.props.mode]}
		label={(active
			? gradio.props.disable_tooltip
			: gradio.props.enable_tooltip) ?? ""}
		disabled={gradio.shared.interactive === false}
		onclick={toggle}
	/>
</div>
