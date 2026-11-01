// Run separately while the app is running: npm run paper:monitor
// The worker must stay running; closing the website does not stop this process.
const url=(process.env.PAPER_MONITOR_URL||'http://localhost:3000')+'/api/setups/monitor';
const secret=process.env.PAPER_MONITOR_SECRET;
if(!secret||secret.length<24)throw new Error('Set PAPER_MONITOR_SECRET (at least 24 characters)');
const delay=Number(process.env.PAPER_MONITOR_INTERVAL_MS||5000);
if(!Number.isInteger(delay)||delay<1000)throw new Error('Invalid monitor interval');
async function tick(){try{const r=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+secret},signal:AbortSignal.timeout(15000)});if(!r.ok)console.error('Monitor HTTP',r.status,await r.text());else{const data=await r.json();if(data.results?.length)console.log(new Date().toISOString(),data.results);}}catch(e){console.error('Monitor unavailable:',e.message);}}
console.log('Paper TP/SL monitor started:',url);
for(;;){await tick();await new Promise(resolve=>setTimeout(resolve,delay));}
