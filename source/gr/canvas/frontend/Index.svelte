<script lang="ts">
	import type { FileData } from "@gradio/client";
	import type {
		CanvasData,
		CanvasEvents,
		CanvasProps,
		DocData,
		DocEventData
	} from "./types";
	import { Block, BlockLabel } from "@gradio/atoms";
	import { Image as ImageIcon } from "@gradio/icons";
	import { StatusTracker } from "@gradio/statustracker";
	import { Gradio } from "@gradio/utils";
	import { onMount, tick, untrack } from "svelte";
	import FullscreenButton from "./FullscreenButton.svelte";
	import { CanvasHost, HOST_EVENT, REQUEST_EVENT, type HostRequest } from "./host";
	import PhotosIcon from "./PhotosIcon.svelte";

	/** Dropped images being uploaded, if any. */
	let upload_promise: Promise<void> | null = null;

	class CanvasGradio extends Gradio<CanvasEvents, CanvasProps> {
		// Events wait for dropped images, to pass them.
		async get_data(): Promise<CanvasProps> {
			if (upload_promise) {
				await upload_promise;
				await tick();
			}
			return super.get_data();
		}
	}

	const props = $props();
	const gradio = new CanvasGradio(props);

	const value: CanvasData = $derived(gradio.props.value ?? { docs: [], index: null });
	const doc: DocData | null = $derived(
		value.index === null ? null : (value.docs[value.index] ?? null)
	);

	let fullscreen = $state(false);
	let drag_over = $state(false);
	/** Whether user drags an image of this canvas, not to drop it here. */
	let internal_drag = false;

	let area: HTMLElement;
	let stage: HTMLElement;
	let image: HTMLImageElement;
	let toolbar: HTMLElement;
	let thumbs: HTMLElement | undefined = $state();
	/** Width of the buttons column: 0 when it has no buttons. */
	let buttons_width = $state(0);

	/** Path of the base layer file: identifies a document. */
	function doc_path(doc: DocData): string {
		return doc.layers[0].object.path;
	}

	function doc_event(index: number): DocEventData {
		return { index, path: doc_path(value.docs[index]) };
	}

	function set_value(docs: DocData[], index: number | null): void {
		gradio.props.value = { docs, index };
	}

	/** Display a document, as user asks. */
	function select(index: number): void {
		if (index === value.index) return;

		set_value(value.docs, index);
		gradio.dispatch("input");
	}

	// Documents as of the last change, to tell what changed.
	let old_paths = untrack(() => value.docs.map(doc_path));
	let old_shown = untrack(() => doc && doc_path(doc));

	// Value set by user or by an event.
	$effect(() => {
		const paths = value.docs.map(doc_path);
		const shown = doc && doc_path(doc);

		untrack(() => dispatch_changes(paths, shown));
	});

	function dispatch_changes(paths: string[], shown: string | null): void {
		if (shown === old_shown && paths.join("\n") === old_paths.join("\n")) {
			return;
		}

		old_paths.forEach((path, index) => {
			if (!paths.includes(path)) gradio.dispatch("doc_deleted", { index, path });
		});
		paths.forEach((path, index) => {
			if (!old_paths.includes(path)) gradio.dispatch("doc_added", { index, path });
		});

		if (old_paths.length && !paths.length) gradio.dispatch("empty");
		else if (!old_paths.length && paths.length) gradio.dispatch("filled");

		if (shown !== old_shown && value.index !== null) {
			gradio.dispatch("select", doc_event(value.index));
		}

		old_paths = paths;
		old_shown = shown;
		gradio.dispatch("change");
	}

	// Thumbnail of the displayed document stays in view.
	$effect(() => {
		const thumb = value.index === null ? null : thumbs?.children[value.index];
		if (!(thumb instanceof HTMLElement)) return;

		thumb.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
		// Focus follows keyboard navigation.
		if (thumbs?.contains(document.activeElement)) thumb.focus({ preventScroll: true });
	});

	// Whether thumbnails are scrolled out before or after: edges fade then.
	let thumbs_before = $state(false);
	let thumbs_after = $state(false);

	function update_thumbs_fades(): void {
		if (!thumbs) return;
		const { scrollLeft, scrollWidth, clientWidth } = thumbs;
		thumbs_before = scrollLeft > 1;
		thumbs_after = scrollLeft + clientWidth < scrollWidth - 1;
	}

	// On resize, and when documents are added or deleted.
	$effect(() => {
		if (!thumbs) return;
		value.docs.length;
		update_thumbs_fades();

		const observer = new ResizeObserver(update_thumbs_fades);
		observer.observe(thumbs);
		return () => observer.disconnect();
	});

	function on_thumb_click(index: number): void {
		gradio.dispatch("thumb_click", doc_event(index));
		select(index);
	}

	function on_thumbs_keydown(event: KeyboardEvent): void {
		const index = value.index;
		const last = value.docs.length - 1;
		if (index === null || event.altKey || event.ctrlKey || event.metaKey) return;

		const moves: Partial<Record<string, number>> = {
			ArrowLeft: Math.max(0, index - 1),
			ArrowRight: Math.min(last, index + 1),
			Home: 0,
			End: last
		};
		const move = moves[event.key];
		if (move === undefined) return;

		event.preventDefault();
		select(move);
	}

	let wheel_delta = 0;

	/** Vertical wheel steps through documents, one per notch even on touchpads. */
	function on_thumbs_wheel(event: WheelEvent): void {
		if (value.index === null || event.ctrlKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
			return;
		}
		event.preventDefault();

		// Line-based deltas (Firefox) to pixels; direction change restarts.
		const delta = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL ? event.deltaY : event.deltaY * 40;
		if (Math.sign(delta) !== Math.sign(wheel_delta)) wheel_delta = 0;
		wheel_delta += delta;
		if (Math.abs(wheel_delta) < 50) return;

		const offset = Math.sign(wheel_delta);
		wheel_delta = 0;
		step(offset);
	}

	/** Display the previous (-1) or next (1) document, if any. */
	function step(offset: number): void {
		if (value.index === null) return;
		select(Math.min(value.docs.length - 1, Math.max(0, value.index + offset)));
	}

	/** Carry the image URL along a drag of an image, which Firefox doesn't. */
	function on_dragstart(event: DragEvent): void {
		const target = event.target;
		if (!(target instanceof HTMLImageElement) || !event.dataTransfer) return;

		internal_drag = true;
		event.dataTransfer.setData("text/uri-list", target.currentSrc);
	}

	function accepts_drop(event: DragEvent): boolean {
		return (
			gradio.shared.interactive !== false &&
			!internal_drag &&
			!!event.dataTransfer?.types.includes("Files")
		);
	}

	function on_dragover(event: DragEvent): void {
		if (!accepts_drop(event)) return;

		event.preventDefault();
		event.dataTransfer!.dropEffect = "copy";
		drag_over = true;
	}

	function on_dragleave(event: DragEvent): void {
		if (!area.contains(event.relatedTarget as Node | null)) drag_over = false;
	}

	function on_drop(event: DragEvent): void {
		drag_over = false;
		if (!accepts_drop(event)) return;

		event.preventDefault();
		const files = [...event.dataTransfer!.files].filter((file) =>
			file.type.startsWith("image/")
		);

		if (files.length) {
			upload_promise = add_files(files).finally(() => (upload_promise = null));
		}
	}

	/** Upload dropped images, then add them, displaying the last one. */
	async function add_files(files: File[]): Promise<void> {
		let uploaded: (FileData | null)[] | null;

		try {
			uploaded = await gradio.shared.client.upload(
				files.map(
					(file): FileData => ({
						path: file.name,
						orig_name: file.name,
						blob: file,
						size: file.size,
						mime_type: file.type,
						is_stream: false,
						meta: { _type: "gradio.FileData" }
					})
				),
				gradio.shared.root,
				undefined,
				gradio.shared.max_file_size ?? undefined
			);
		} catch (error) {
			gradio.dispatch("error", error instanceof Error ? error.message : String(error));
			return;
		}

		const added = (uploaded ?? [])
			.filter((object) => object !== null)
			.map(
				(object): DocData => ({
					layers: [{ object, imported: true, source_file: null }],
					caption: null
				})
			);
		if (!added.length) return;

		const first = value.docs.length;
		set_value([...value.docs, ...added], first + added.length - 1);

		added.forEach((_doc, i) => gradio.dispatch("doc_dropped", doc_event(first + i)));
		gradio.dispatch("input");
	}

	onMount(() => {
		const host = new CanvasHost(
			gradio.shared.id,
			stage,
			image,
			area,
			toolbar,
			gradio.props.tools ?? []
		);

		host.addEventListener("tool-change", () =>
			gradio.dispatch("tool_selected", { tool: host.tool })
		);

		const on_request = (event: Event): void => {
			const request = (event as CustomEvent<HostRequest>).detail;
			if (request.canvas_id === host.id) request.resolve(host);
		};

		window.addEventListener(REQUEST_EVENT, on_request);
		window.dispatchEvent(new CustomEvent(HOST_EVENT, { detail: host }));

		return () => window.removeEventListener(REQUEST_EVENT, on_request);
	});
</script>

<Block
	visible={gradio.shared.visible}
	variant="solid"
	padding={false}
	elem_id={gradio.shared.elem_id}
	elem_classes={gradio.shared.elem_classes}
	container={gradio.shared.container}
	scale={gradio.shared.scale}
	min_width={gradio.shared.min_width}
	allow_overflow={false}
	height={gradio.props.height ?? undefined}
	bind:fullscreen
>
	<StatusTracker
		autoscroll={gradio.shared.autoscroll}
		i18n={gradio.i18n}
		{...gradio.shared.loading_status}
		on_clear_status={() =>
			gradio.dispatch("clear_status", gradio.shared.loading_status)}
	/>
	<BlockLabel
		show_label={gradio.shared.show_label}
		Icon={ImageIcon}
		label={gradio.shared.label || "Canvas"}
	/>

	<div
		class="canvas"
		class:drag-over={drag_over}
		bind:this={area}
		role="group"
		aria-label={gradio.shared.label}
		ondragstart={on_dragstart}
		ondragend={() => (internal_drag = false)}
		ondragover={on_dragover}
		ondragleave={on_dragleave}
		ondrop={on_drop}
	>
		<!-- Inset on both sides, to keep the image centered and clear of buttons. -->
		<div
			class="stage"
			class:hidden={!doc}
			style:margin-inline={buttons_width
				? `calc(${buttons_width}px + var(--spacing-lg))`
				: undefined}
			bind:this={stage}
		>
			<img
				class="layer"
				bind:this={image}
				src={doc?.layers[0].object.url}
				alt=""
			/>
			{#each doc?.layers.slice(1) ?? [] as layer}
				<img class="layer" src={layer.object.url} alt="" />
			{/each}
		</div>

		{#if !doc}
			<div class="placeholder">
				<div class="placeholder-art" aria-hidden="true">
					<PhotosIcon />
				</div>
				{#if gradio.props.placeholder}<p>{gradio.props.placeholder}</p>{/if}
			</div>
		{/if}

		{#if value.docs.length}
			<!-- Arrows on hover, for mouse users: keys already step. -->
			<div class="thumbs-bar" onwheel={on_thumbs_wheel}>
				<button
					class="thumbs-arrow"
					tabindex="-1"
					aria-label="Previous"
					disabled={!value.index}
					onclick={() => step(-1)}
				>
					<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 4L6 8L10 12" /></svg>
				</button>
				<div
					class="thumbs"
					class:fade-start={thumbs_before}
					class:fade-end={thumbs_after}
					role="listbox"
					aria-orientation="horizontal"
					tabindex="-1"
					bind:this={thumbs}
					onkeydown={on_thumbs_keydown}
					onscroll={update_thumbs_fades}
				>
					{#each value.docs as thumb_doc, i}
						<button
							class="thumb"
							role="option"
							aria-selected={i === value.index}
							title={thumb_doc.caption ?? undefined}
							onclick={() => on_thumb_click(i)}
						>
							{#each thumb_doc.layers as layer}
								<img class="layer" src={layer.object.url} alt="" loading="lazy" />
							{/each}
						</button>
					{/each}
				</div>
				<button
					class="thumbs-arrow"
					tabindex="-1"
					aria-label="Next"
					disabled={value.index === null || value.index === value.docs.length - 1}
					onclick={() => step(1)}
				>
					<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4L10 8L6 12" /></svg>
				</button>
			</div>
		{/if}

		<!-- Actions, then tools in a column below. A click keeps focus where it
		     was, e.g. in a prompt: else a shortcut pressed later, e.g. F, shows
		     the focus ring on the button. -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="buttons"
			class:below-label={gradio.shared.show_label}
			bind:offsetWidth={buttons_width}
			onmousedown={(event) => event.preventDefault()}
		>
			{#if gradio.props.buttons?.includes("fullscreen")}
				<div class="group">
					<FullscreenButton
						{fullscreen}
						onclick={(is_fullscreen) => (fullscreen = is_fullscreen)}
						label={gradio.props.fullscreen_tooltip}
						exit_label={gradio.props.exit_fullscreen_tooltip}
						hovered={() => area.matches(":hover")}
					/>
				</div>
			{/if}
			<div class="group toolbar" role="toolbar" bind:this={toolbar}></div>
		</div>
	</div>
</Block>

<style>
	.canvas {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--spacing-lg);
		height: 100%;
		padding-bottom: var(--spacing-lg);
	}

	.canvas.drag-over {
		outline: 1px solid var(--color-accent);
		outline-offset: -1px;
	}

	.stage {
		position: relative;
		flex: 1;
		min-height: 0;
	}

	.stage.hidden {
		display: none;
	}

	.layer {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
	}

	/* Centered on the whole canvas, ignoring its bottom padding. */
	.placeholder {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--spacing-xxl);
		color: var(--body-text-color-subdued);
		text-align: center;
	}

	.placeholder p {
		margin: 0;
	}

	/* Large, above the placeholder text. */
	.placeholder-art {
		flex: 0 1 34%;
		align-self: stretch;
		min-height: 0;
		opacity: 0.9;
		pointer-events: none;
	}

	.thumbs-bar {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		padding-inline: var(--spacing-sm);
	}

	/* Hidden until hovered, and at either end. */
	.thumbs-arrow {
		flex-shrink: 0;
		width: var(--size-6);
		height: var(--size-6);
		padding: var(--spacing-xxs);
		color: var(--body-text-color-subdued);
		opacity: 0;
		transition: opacity 0.15s;
	}

	.thumbs-bar:hover .thumbs-arrow:not(:disabled) {
		opacity: 1;
	}

	.thumbs-arrow:hover {
		color: var(--body-text-color);
	}

	.thumbs-arrow svg {
		width: 100%;
		height: 100%;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.thumbs {
		display: flex;
		flex: 1;
		min-width: 0;
		justify-content: safe center;
		gap: var(--spacing-lg);
		padding: 2px var(--spacing-lg);
		overflow-x: auto;
		/* Thumbnail scrolled into view stays clear of the fades. */
		scroll-padding-inline: var(--size-4);
		scrollbar-width: none;
		/* Thumbnails scrolled out fade at the edges, into the background. */
		--fade-start: 0px;
		--fade-end: 0px;
		mask-image: linear-gradient(
			to right,
			transparent,
			#000 var(--fade-start),
			#000 calc(100% - var(--fade-end)),
			transparent
		);
	}

	.thumbs.fade-start {
		--fade-start: var(--size-4);
	}

	.thumbs.fade-end {
		--fade-end: var(--size-4);
	}

	.thumb {
		position: relative;
		flex-shrink: 0;
		width: var(--size-20);
		height: var(--size-20);
		border-radius: var(--button-small-radius);
		background: var(--background-fill-secondary);
		overflow: clip;
	}

	.thumb .layer {
		object-fit: cover;
		/* Composited: Chromium aliases large reductions otherwise. */
		will-change: transform;
	}

	.thumb:hover {
		filter: brightness(1.1);
	}

	.thumb[aria-selected="true"] {
		/* Outside, within the strip padding: images would cover an inset one. */
		outline: 2px solid var(--body-text-color);
	}

	/* In the top left corner, away from the window Close button users could
	   hit instead, e.g. in ZPix on Windows. Styled as IconButtonWrapper in a
	   top panel, mirrored. */
	.buttons {
		position: absolute;
		top: var(--block-label-margin);
		left: var(--block-label-margin);
		z-index: var(--layer-2);
		display: flex;
		flex-direction: column;
		gap: var(--spacing-sm);
		border: 1px solid var(--border-color-primary);
		border-top: none;
		border-left: none;
		border-radius: var(--block-label-radius);
		background: var(--block-background-fill);
		box-shadow: var(--shadow-drop);
		padding: var(--spacing-sm);
	}

	.buttons:not(:has(.group:not(:empty))) {
		display: none;
	}

	/* Label margin may be a unitless 0, unfit for calc(). */
	.buttons.below-label {
		top: var(--size-9);
	}

	.group {
		display: flex;
		flex-direction: column;
		gap: var(--spacing-sm);
	}

	/* Separator between buttons, as in IconButtonWrapper. */
	.group:not(:empty) ~ .group:not(:empty)::before,
	.group :global(> :not([hidden]) ~ :not([hidden]))::before {
		content: "";
		align-self: center;
		width: 60%;
		height: 1px;
		background-color: var(--border-color-primary);
	}

	.group :global(> :not([hidden]) ~ :not([hidden])) {
		display: flex;
		flex-direction: column;
		gap: var(--spacing-sm);
	}

	/* Larger than IconButton default, for actions and tools alike. Margin
	   keeps hover background off the panel edges, as in IconButtonWrapper. */
	.group :global(.icon-button) {
		margin: var(--spacing-xxs);
		border-radius: var(--radius-xs);
		padding: var(--spacing-xxs);
	}

	.group :global(.icon-button > div) {
		width: 18px;
		height: 18px;
	}

	/* Active tool, as hovered. */
	.toolbar :global(.icon-button[aria-pressed="true"]) {
		background-color: var(--background-fill-secondary);
	}

	.toolbar:empty {
		display: none;
	}
</style>
