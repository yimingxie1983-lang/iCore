import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const p=await PresentationFile.importPptx(await FileBlob.load("D:/Codex/Code/iCore/cancer_claw_share_20260722_1757/ppt_work/template-starter.pptx"));
console.log(await p.inspect({kind:"slide,shape,textbox,image,notes",maxChars:20000}).then(x=>x.ndjson));
