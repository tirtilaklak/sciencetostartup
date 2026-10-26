/* Negative observations from public link checks. No requests or contact changes. */
(() => {
  'use strict';
  const labels={not_found:'Page unavailable',gone:'Page unavailable',sign_in:'Asks for sign-in'};
  const publicURL=value=>{
    if(typeof value!=='string')return '';
    try{
      const url=new URL(value),host=url.hostname.toLowerCase().replace(/\.$/,'');
      if(!['https:','http:'].includes(url.protocol)||url.username||url.password||!host.includes('.')||host.includes(':')||/(?:^|\.)(?:localhost|local|internal|test|invalid)$/.test(host))return '';
      if([...url.searchParams.keys()].some(key=>/(?:^|[-_])(?:token|api[-_]?key|password|passwd|secret|credential|signature)(?:$|[-_])/i.test(key)))return '';
      const octets=/^\d+\.\d+\.\d+\.\d+$/.test(host)?host.split('.').map(Number):null;
      if(octets&&(octets[0]===0||octets[0]===10||octets[0]===127||octets[0]>=224||octets[0]===169&&octets[1]===254||octets[0]===172&&octets[1]>=16&&octets[1]<=31||octets[0]===192&&octets[1]===168||octets[0]===100&&octets[1]>=64&&octets[1]<=127||octets[0]===198&&[18,19].includes(octets[1])))return '';
      url.hash='';return url.href;
    }catch{return '';}
  };
  const checkedDate=value=>{
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return '';
    const date=new Date(value+'T12:00:00Z');
    return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value?value:'';
  };
  const entries=new Map();
  for(const entry of Array.isArray(window.LINK_HEALTH?.entries)?window.LINK_HEALTH.entries:[]){
    if(!entry||!Object.hasOwn(labels,entry.status))continue;
    const url=publicURL(entry.url),date=checkedDate(entry.checked_on);
    if(url&&date&&(!entries.has(url)||date>=entries.get(url).checked_on))entries.set(url,{status:entry.status,checked_on:date});
  }
  // One formatter and one cached badge per link: building them per call was a startup hot spot.
  const dayFormat=new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}),badges=new Map();
  const availabilityHTML=url=>{
    const entry=entries.get(publicURL(url));if(!entry)return '';
    const display=dayFormat.format(new Date(entry.checked_on+'T12:00:00Z')).replace('Sept','Sep');
    const observation=entry.status==='sign_in'?`When we checked on ${display} without an account, the page asked us to sign in.`:`Page unavailable when checked ${display}.`;
    return `<span class="source-link-status" data-link-status="${entry.status}" title="${observation}"><span aria-hidden="true">${labels[entry.status]} · <time datetime="${entry.checked_on}">${display}</time></span><span class="sr-only">${observation}</span></span>`;
  };
  window.linkAvailabilityHTML=url=>{if(!badges.has(url))badges.set(url,availabilityHTML(url));return badges.get(url);};
})();
