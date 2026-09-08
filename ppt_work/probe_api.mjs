import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const p=await PresentationFile.importPptx(await FileBlob.load("D:/Codex/Code/iCore/cancer_claw_share_20260722_1757/ppt_work/template-starter.pptx"));
const s=p.slides.items[0];
console.log('slide keys', Reflect.ownKeys(s));
console.log('shapes keys', Reflect.ownKeys(s.shapes));
console.log('shapes items length', s.shapes.items?.length);
console.log('shapes items', s.shapes.items?.map(x=>({aid:x.aid,id:x.id,name:x.name,constructor:x.constructor?.name,keys:Reflect.ownKeys(x).slice(0,20)})));
console.log('placeholders', Reflect.ownKeys(s.placeholders), s.placeholders.items?.map(x=>({aid:x.aid,id:x.id,name:x.name,type:x.type})));
