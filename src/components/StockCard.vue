<template>
  <div class="card">

    <div class="name">
      {{ stock.name }}
    </div>

    <div class="price">
      {{ stock.price }}
    </div>

    <div
      class="change"
      :class="stock.change >= 0 ? 'up':'down'"
    >
      {{ stock.change >= 0 ? '+' : '' }}
      {{ stock.change }}%
    </div>

  </div>
</template>


<script setup>

defineProps({

  stock:{
    type:Object,
    required:true
  }

})

</script>


<style scoped>

.card{

background:white;

border-radius:16px;

padding:20px;

box-shadow:0 4px 15px rgba(0,0,0,.08);

width:220px;

}


.name{

font-size:18px;

font-weight:bold;

}


.price{

font-size:32px;

margin:15px 0;

}


.up{

color:#e53935;

}


.down{

color:#16a34a;

}

</style>
