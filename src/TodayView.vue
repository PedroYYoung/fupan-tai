<template>

  <div class="page">

    <h1>今日行情</h1>


    <div class="date">
      日期：{{ market.date }}
    </div>


    <div class="cards">

      <div
        class="card"
        v-for="item in market.quotes"
        :key="item.code"
      >

        <div class="name">
          {{ item.name }}
        </div>


        <div class="code">
          {{ item.code }}
        </div>


        <div class="price">
          {{ item.price }}
        </div>


        <div
          class="change"
          :class="item.change >= 0 ? 'up':'down'"
        >

          {{ item.change >= 0 ? '+' : '' }}
          {{ item.change }}%

        </div>


      </div>

    </div>


  </div>


</template>



<script setup>

import { ref,onMounted } from "vue"


const market = ref({

  date:"",

  quotes:[]

})



async function loadData(){

  const res = await fetch("/data/quotes.json")

  const json = await res.json()

  market.value = json

}



onMounted(()=>{

  loadData()

})


</script>



<style scoped>


.page{

padding:30px;

}



h1{

font-size:32px;

margin-bottom:10px;

}



.date{

color:#888;

margin-bottom:25px;

}



.cards{

display:flex;

gap:20px;

flex-wrap:wrap;

}



.card{

width:220px;

background:white;

border-radius:16px;

padding:20px;

box-shadow:
0 5px 20px rgba(0,0,0,.08);

}



.name{

font-size:20px;

font-weight:bold;

}



.code{

color:#888;

margin-top:5px;

}



.price{

font-size:34px;

font-weight:bold;

margin:20px 0;

}



.change{

font-size:20px;

font-weight:bold;

}



.up{

color:red;

}



.down{

color:green;

}


</style>
