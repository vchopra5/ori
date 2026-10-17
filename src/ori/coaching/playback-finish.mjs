// A presentation flourish, not a claim that a physics/video check passed.
export function playbackFinish(host){
  const overlay=document.createElement('div');overlay.className='playback-finish';
  const label=document.createElement('div');label.className='playback-finish-label';label.setAttribute('role','status');label.textContent='And there it is. ✨';overlay.append(label);host.append(overlay);
  const animations=[];
  if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
    const colors=['#d96950','#a18bce','#86ad97','#e6c87f','#f7ece0'];
    for(let i=0;i<54;i++){
      const piece=document.createElement('i');piece.className='finish-confetti';piece.style.background=colors[i%colors.length];piece.style.borderRadius=i%3===0?'50%':'2px';overlay.append(piece);
      const spread=Math.min(host.clientWidth*.45,330),x=(Math.random()-.5)*2*spread,up=-(90+Math.random()*130),fall=host.clientHeight*.7,spin=(Math.random()-.5)*900;
      animations.push(piece.animate([
        {transform:'translate(0,0) rotate(0deg)',opacity:0},
        {transform:`translate(${x*.35}px,${up}px) rotate(${spin*.3}deg)`,opacity:1,offset:.28},
        {transform:`translate(${x*.8}px,${up*.2}px) rotate(${spin*.7}deg)`,opacity:1,offset:.6},
        {transform:`translate(${x}px,${fall}px) rotate(${spin}deg)`,opacity:0}
      ],{duration:1800+Math.random()*500,delay:Math.random()*130,easing:'linear',fill:'both'}));
    }
  }
  const timer=setTimeout(()=>overlay.querySelectorAll('.finish-confetti').forEach(p=>p.remove()),2500);
  return ()=>{clearTimeout(timer);animations.forEach(a=>a.cancel());overlay.remove();};
}
