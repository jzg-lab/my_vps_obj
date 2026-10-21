<script lang="ts">
  import UserServices from "./services/UserServices.svelte";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  let { at }: { at: ServiceTranslate } = $props();
</script>

<UserServices {at} userId={null} />
