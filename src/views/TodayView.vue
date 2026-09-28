<template>
  <div class="page">

    <h1>复盘台</h1>

    <p class="date">
      更新时间：{{ data.date }}
    </p>


    <div class="cards">

      <div
        v-for="item in data.quotes"
        :key="item.code"
        class="card"
      >

        <h2>
          {{ item.name }}
        </h2>


        <div class="price">
          {{ item.price }}
        </div>


        <div
          :class="item.change >= 0 ? 'up':'down'"
        >
          {{ item.change >=0 ? '+' : '' }}
          {{ item.change }}%
        </div>


      </div>


    </div>


  </div>
</template>


<script setup>

import {
  ref,
  onMounted
} from "vue"


const data = ref({

  date:"",
  quotes:[]

})


async function load(){

  const res =
    await fetch("/data/quotes.json")

  data.value =
    await res.json()

}


onMounted(load)


</script>


<style scoped>

.page{

 padding:30px;

}


.cards{

 display:flex;

 gap:20px;

 flex-wrap:wrap;

}


.card{

 border:1px solid #ddd;

 border-radius:12px;

 padding:20px;

 width:220px;

}


.price{

 font-size:32px;

 margin:15px 0;

}


.up{

 color:red;

}


.down{

 color:green;

}


</style>
