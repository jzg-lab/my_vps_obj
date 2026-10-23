<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { BrandConfig } from "$lib/webapp/types.js";
  import ThemeEffectSurface from "./ThemeEffectSurface.svelte";

  let { brand, brandTitle }: { brand: BrandConfig; brandTitle: string } = $props();
</script>

<div class="login-brand home-brand" style="position:relative;isolation:isolate">
  <ThemeEffectSurface name="home.header.surface" />
  <div class="home-logo-slot">
    <BrandMark {brand} size="xl" />
  </div>
  <h1>{brandTitle}</h1>
</div>
