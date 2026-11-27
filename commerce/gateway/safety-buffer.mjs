export function bufferAvailable(level,buffer=0){
 const rawStocked=level?.stocked_quantity,rawReserved=level?.reserved_quantity;
 for(const value of [rawStocked,rawReserved]){
  if(value===null||typeof value==='boolean'||(typeof value==='string'&&value.trim()==='')){
   throw new Error('Inventory availability needs review.');
  }
 }
 const stocked=Number(rawStocked),reserved=Number(rawReserved);
 if(!Number.isSafeInteger(stocked)||!Number.isSafeInteger(reserved)||stocked<0||reserved<0||!Number.isSafeInteger(buffer)||buffer<0)throw new Error('Inventory availability needs review.');
 return Math.max(0,stocked-reserved-buffer);
}
