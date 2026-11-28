import {productDetails} from './product-details.mjs';
// Interpretation only. Commerce arithmetic and authorization never run in the interpreter.
const detailLabels={description:'description', 'package size':'package_size',ingredients:'ingredients',allergens:'allergens',handling:'handling',category:'category'};
const detailField=new RegExp(String.raw`^\s*(?:${Object.keys(detailLabels).join('|')})\s*[:=]`,'i');

function stockCue(words) {
 const cue=String.raw`\b(?:${words})\b`;
 const units='(?:each|jars?|bottles?|bags?|loaf|loaves|bunch(?:es)?|box(?:es)?)';
 return new RegExp([
  String.raw`\b\d+\s*(?:${units}\s+)?(?:(?:is|are)\s+)?${cue}`, // 12 new jars; 12 jars total
  String.raw`${cue}\s*(?:of\s+|[:=]\s*)?\d+\b`, // received 12; total of 12
  String.raw`(?:^|[;,\n])\s*(?:(?:a|the)\s+)?${cue}(?:\s+for\s+online(?:\s+pickup)?)?\s*[.!]?\s*(?=$|[;,\n])` // direct stock reply
 ].join('|'),'i');
}
const receiptCue=stockCue(String.raw`new(?:\s+(?:arrival|stock))?|received|arrival`);
const recountCue=stockCue(String.raw`(?:total\s+)?(?:now\s+)?available|total|recount`);

export function interpret(message, previous={}) {
 const f={...previous}; const t=message.trim();
 // Prefer explicitly delimited identity; never name a shelf as a product.
 const name=t.match(/(?:product|name)\s*[:=]\s*([^;\n]+)/i);
 if(name) f.name=name[1].trim();
 const simple=t.match(/^([^,;\n]{2,80}),\s*(each|jar|bottle|bag|loaf|bunch|box),\s*\$/i);if(simple){f.name=simple[1].trim();f.unit=simple[2].toLowerCase()}
 const namedPrice=t.match(/^([^,;\n]{2,80}),\s*\$/);if(!f.name&&namedPrice&&!/^(?:these|this|those|it)\b/i.test(namedPrice[1]))f.name=namedPrice[1].trim();
 if(/\$\s*[^;\n,]+/.test(t))delete f.price_minor;
 const price=t.match(/\$\s*(\d+(?:\.\d{1,2})?)(?![\d.]|,\d)(?:\s*(?:\/|per\s+)?(each|jar|bottle|bag|loaf|bunch|box|lb|pound)\b)?/i);
 if(price){f.price_minor=Math.round(Number(price[1])*100);if(price[2])f.unit=price[2].toLowerCase();}
 const unit=t.match(/(?:unit)\s*[:=]\s*(each|jar|bottle|bag|loaf|bunch|box|lb|pound)\b/i);if(unit)f.unit=unit[1].toLowerCase();
 const listing=simple||namedPrice;
 const stockText=t.split(/[;\n]/).map((part,index)=>{
  if(detailField.test(part))return '';
  if(index===0&&listing)return part.slice(listing[1].length);
  return part.replace(/^\s*(?:product|name)\s*[:=][^,$]*/i,'');
 }).join(';').replace(/\$\s*[+-]?[\d.,]*\d/g,'$'); // Keep $ so a price total is not a standalone stock reply.
 if(/(?:quantity|qty)\s*[:=]|\d[\d.,-]*\s*(?:available|total|new|jars|bottles|bags|loaves|bunches|boxes|each)\b/i.test(stockText))delete f.quantity;
 const qty=stockText.match(/(?:quantity|qty)\s*[:=]\s*(\d+)(?![\d.,])(?=\s|;|$)/i)||stockText.match(/(?<![\d.,-])(\d+)\s*(?:available|total|new|jars|bottles|bags|loaves|bunches|boxes|each)\b/i);
 if(qty)f.quantity=Number(qty[1]);
 if(/(?:online\s+(?:pickup|stock|bin)|for\s+online)/i.test(t)) f.stock_pool='online';
 const action=t.match(/(?:action)\s*[:=]\s*(receipt|recount|transfer|correction)/i);
 if(action)f.stock_action=action[1].toLowerCase();
 else if(receiptCue.test(stockText))f.stock_action='receipt';
 else if(recountCue.test(stockText))f.stock_action='recount';
 for(const [label,key] of Object.entries(detailLabels)){const match=t.match(new RegExp('(?:^|[;\\n])\\s*'+label+'\\s*[:=]\\s*([^;\\n]*)','i'));if(match)f[key]=match[1].trim();}
 Object.assign(f,productDetails(f));if(f.category!==undefined&&(typeof f.category!=='string'||!f.category||f.category.length>80))throw Object.assign(new Error('Use a category name between 1 and 80 characters.'),{status:422});
 if(/\b(?:cider|alcohol|wine|beer)\b/i.test(f.name||''))f.restricted=true;
 return {fields:f,questions:questions(f),interpreter:'local-rules',note:'Only explicit text fields are extracted. Photo labels are evidence for review; no price or stock is inferred from a picture.'};
}
export function questions(f){const q=[];if(!f.name?.trim())q.push('What is this product called, including its variant or package size?');if(!f.unit)q.push('What is the selling unit?');else if(!['each','jar','bottle','bag','loaf','bunch','box'].includes(f.unit))q.push('Choose a fixed-price selling unit or a confirmed prepacked package. Weighed-at-pickup sales are not enabled.');if(!Number.isSafeInteger(f.price_minor)||f.price_minor<=0)q.push('What is the price per selling unit?');if(!Number.isSafeInteger(f.quantity)||f.quantity<0)q.push('How many selling units are allocated to online pickup?');if(f.stock_pool!=='online')q.push('Is this quantity in the marked online bin?');if(!['receipt','recount'].includes(f.stock_action))q.push('Is this a new arrival or the total now available?');if(f.restricted||/\b(?:cider|alcohol|wine|beer)\b/i.test(f.name||''))q.push('This item is held for restricted-product review and cannot be approved for checkout.');return q;}
export function validateFields(f){const q=questions(f);if(q.length)throw Object.assign(new Error(q.join(' ')),{status:422});if(!['each','jar','bottle','bag','loaf','bunch','box'].includes(f.unit))throw Object.assign(new Error('Use a fixed-price selling unit or a named prepacked weight for this first build.'),{status:422});return f;}
export function assertVersion(d,version){if(!Number.isSafeInteger(version)||d.version!==version)throw Object.assign(new Error('The draft changed. Review the current version before approving.'),{status:409});}
