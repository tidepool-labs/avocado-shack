export function pickupCommand(message){
 const match=message.trim().match(/^(close|reopen) pickup(?: on)?\s+(.+)$/i);if(!match)return null;
 const date=match[2].replace(/[.]$/,'').trim();if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+'T12:00:00Z'))||new Date(date+'T12:00:00Z').toISOString().slice(0,10)!==date)throw Object.assign(new Error('Use an exact pickup date: YYYY-MM-DD.'),{status:422});
 return {date,active:match[1].toLowerCase()==='reopen'};
}

export function assertPickupWindows(proposed,current){
 const remaining=new Map(proposed.map(s=>[s.id,s.version]));
 const conflict=()=>Object.assign(new Error('The pickup windows changed or expired. Send a new request and review it.'),{status:409});
 if(!current.length||remaining.size!==proposed.length||current.length!==remaining.size)throw conflict();
 for(const {id,version} of current){
  if(!remaining.has(id)||remaining.get(id)!==version)throw conflict();
  remaining.delete(id);
 }
}
