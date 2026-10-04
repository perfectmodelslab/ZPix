<script lang="ts">
	import type { BoundingBox } from "./overlay";

	export let value: BoundingBox | null;
	export let type: "gallery" | "table";
	export let selected = false;
</script>

<div
	class:table={type === "table"}
	class:gallery={type === "gallery"}
	class:selected
>
	{#if value}
		{value.x}, {value.y} · {value.width}×{value.height}
	{:else}
		—
	{/if}
</div>

<style>
	.gallery {
		padding: var(--size-1) var(--size-2);
	}

	div {
		overflow: hidden;
		white-space: nowrap;
	}
</style>
