import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workDir = "D:/Codex/Code/iCore/cancer_claw_share_20260722_1757/ppt_work";
const starterPath = path.join(workDir, "template-starter.pptx");
const finalPath = path.join(workDir, "final.pptx");
const renderDir = path.join(workDir, "final-renders");
const layoutDir = path.join(workDir, "final-layout");

const NAVY = "#071F58";
const NAVY_SOFT = "#254A8D";
const BODY = "#2F3B4B";
const MUTED = "#5A6677";
const PANEL = "#F4F7FC";
const PANEL_LINE = "#D6E0F0";
const ACCENT = "#EE822F";
const WARN_BG = "#FFF7E9";
const WARN_LINE = "#F1C46B";
const CALIBRI = "Calibri";

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function addSurface(slide, name, x, y, w, h, fill, line = PANEL_LINE) {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    // Keep inherited layout/master furniture visible and avoid opaque mask overlays.
    fill: "none",
    line: { style: "solid", fill: line, width: 1 },
  });
}

function addText(slide, name, x, y, w, h, text, style) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = { typeface: CALIBRI, ...style };
  return shape;
}

function addRule(slide, name, x, y, w, color = "#BFCBD9") {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: { left: x, top: y, width: w, height: 1 },
    fill: color,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

function addStep(slide, index, x, y, w, heading, detail) {
  const badge = slide.shapes.add({
    geometry: "ellipse",
    name: `workflow-step-${index}-no`,
    position: { left: x, top: y, width: 22, height: 22 },
    fill: ACCENT,
    line: { style: "solid", fill: "none", width: 0 },
  });
  badge.text = String(index);
  badge.text.style = { fontSize: 13, bold: true, color: "#FFFFFF", typeface: CALIBRI };
  addText(slide, `workflow-step-${index}-heading`, x + 32, y, w - 32, 20, heading, {
    fontSize: 14,
    bold: true,
    color: NAVY,
  });
  addText(slide, `workflow-step-${index}-detail`, x + 32, y + 23, w - 32, 48, detail, {
    fontSize: 12,
    color: BODY,
  });
}

function findShape(slide, name) {
  const object = slide.shapes.items.find((shape) => shape.name === name);
  if (!object) throw new Error(`Shape not found: ${name}`);
  return object;
}

function findImage(slide, name) {
  const object = slide.images.items.find((image) => image.name === name);
  if (!object) throw new Error(`Image not found: ${name}`);
  return object;
}

function prepareClonedSlide(slide) {
  findShape(slide, "标题 1").delete();
  findShape(slide, "副标题 2").delete();
  findImage(slide, "图片 7").delete();
  return {
    slide,
    title: findShape(slide, "title-11"),
    page: findShape(slide, "page-11"),
  };
}

async function main() {
  const presentation = await PresentationFile.importPptx(await FileBlob.load(starterPath));

  // Shared cloned-frame edits. Empty inherited placeholders are deleted in the edit plan.
  const slideSpec1 = prepareClonedSlide(presentation.slides.items[0]);
  const slideSpec2 = prepareClonedSlide(presentation.slides.items[1]);

  // ---------- Slide 1: clinical decision support ----------
  const slide1 = slideSpec1.slide;
  const title1 = slideSpec1.title;
  title1.text = "案例｜iCore 临床辅助诊断：多源病历证据整合与下一步优先级";
  title1.text.style = { fontSize: 25.5, bold: true, color: NAVY, typeface: CALIBRI };
  const page1 = slideSpec1.page;
  page1.text = "1";
  page1.text.style = { fontSize: 14, bold: true, color: NAVY, typeface: CALIBRI };

  addSurface(slide1, "dx-workflow-band", 40, 150, 1200, 106, PANEL, PANEL_LINE);
  addText(slide1, "dx-workflow-title", 64, 166, 320, 24, "iCore 工作流", {
    fontSize: 18,
    bold: true,
    color: NAVY,
  });
  addText(slide1, "dx-workflow-subtitle", 64, 193, 320, 42, "把非结构化病历转成\n可核验、可讨论的决策材料", {
    fontSize: 12,
    color: BODY,
  });
  const dxSteps = [
    ["病历抽取", "主诉、超声/钼靶、穿刺、IHC、FISH、家族史"],
    ["关键锚定", "HER2 扩增、ER-low、Ki-67、cN1、Ⅰ/ⅡB 分期"],
    ["循证检索", "NeoSphere、TRAIN-2、KATHERINE、POEMS、ER-low"],
    ["医生确认", "鉴别、补充检查、治疗选项交经治医师与 MDT"],
  ];
  dxSteps.forEach((step, i) => addStep(slide1, i + 1, 390 + i * 213, 172, 198, step[0], step[1]));
  addRule(slide1, "dx-workflow-split", 386, 164, 1, "#BFCBD9");

  addSurface(slide1, "dx-patient-panel", 40, 276, 350, 320, "#FFFFFF", PANEL_LINE);
  addText(slide1, "dx-patient-heading", 64, 296, 300, 22, "病例事实（合成 A001）", {
    fontSize: 17,
    bold: true,
    color: NAVY,
  });
  addRule(slide1, "dx-patient-rule", 64, 326, 302, "#D6E0F0");
  addText(
    slide1,
    "dx-patient-body",
    64,
    340,
    305,
    235,
    [
      "• 患者：38 岁未绝经女性，右乳无痛性增大肿块",
      "• 病理：浸润性癌 NST / IDC-NOS，Nottingham 3 级",
      "• 分子：HER2 IHC 2+，FISH HER2/CEP17=4.2 扩增；ER 8%，Ki-67 45%",
      "• 分期：cT2N1M0，AJCC ⅡB 期",
      "• 家族史：母亲 52 岁乳腺癌，姨母 55 岁卵巢癌",
    ].join("\n"),
    { fontSize: 13.2, color: BODY },
  );

  addSurface(slide1, "dx-output-panel", 410, 276, 830, 152, "#FFFFFF", PANEL_LINE);
  addText(slide1, "dx-output-heading", 434, 294, 500, 22, "iCore 辅助判断输出", {
    fontSize: 17,
    bold: true,
    color: NAVY,
  });
  addText(
    slide1,
    "dx-output-body",
    434,
    326,
    785,
    91,
    [
      "• 核心分型：HER2 阳性型、ER-low、高增殖；腋窝淋巴结影像可疑（cN1），需病理证实",
      "• 鉴别排除：纤维腺瘤、增生结节、乳头状瘤、小叶癌、基底样/三阴性、炎性乳腺癌",
      "• 循证支撑：新辅助双靶与术后 T-DM1 阶梯均引用已核验 PMID，不用裸结论",
    ].join("\n"),
    { fontSize: 13.2, color: BODY },
  );

  addSurface(slide1, "dx-next-panel", 410, 448, 830, 148, "#FFFFFF", PANEL_LINE);
  addText(slide1, "dx-next-heading", 434, 466, 500, 22, "下一步优先级（供临床确认）", {
    fontSize: 17,
    bold: true,
    color: NAVY,
  });
  addText(
    slide1,
    "dx-next-body",
    434,
    498,
    785,
    86,
    [
      "① 胚系 BRCA1/2 检测 + 遗传咨询：直接影响手术范围与对侧/卵巢风险管理",
      "② 基线 LVEF/ECG 与腋窝淋巴结穿刺或标记夹：治疗前安全与准确分期",
      "③ 生殖医学评估生育力保存；新辅助选项 TCHP / THP，非 pCR 后考虑 T-DM1",
    ].join("\n"),
    { fontSize: 13.2, color: BODY },
  );

  addSurface(slide1, "dx-safety-strip", 40, 632, 1200, 34, WARN_BG, WARN_LINE);
  addText(
    slide1,
    "dx-safety-text",
    64,
    639,
    1160,
    22,
    "安全边界：A001 为合成数字孪生病历，非真实患者；iCore 只做证据整理与选项排序，最终诊断和治疗方案由经治医师结合患者意愿与 MDT 决定。",
    { fontSize: 12, bold: true, color: "#7A4A00" },
  );

  slide1.speakerNotes.textFrame.setText([
    "案例定位：展示 iCore 把多源临床材料压缩为可核验的鉴别诊断与行动优先级，而非替代医生判断。",
    "病例来源：iCore“数据清洗”项目 digital_twins/乳腺癌数字孪生病历_A001.md 与 数字孪生病历_A001_鉴别诊断与治疗建议.md（2026-08-16）。该病例为合成数据。",
    "关键事实：38 岁女性；右乳浸润性癌 NST，G3；HER2 IHC 2+，FISH 比值 4.2；ER 8%，Ki-67 45%；cT2N1M0 ⅡB 期；母亲乳腺癌、姨母卵巢癌家族史。",
    "输出逻辑：主诉/影像/检验锚定 HER2 阳性 ER-low 高增殖；鉴别排除纤维腺瘤、增生结节、小叶癌、三阴性/基底样、炎性乳腺癌；cN1 需病理证实。",
    "[Sources] 项目内证据：digital_twins/数字孪生病历_A001_鉴别诊断与治疗建议.md； PubMed 已核验引用：TRAIN-2 [PMID:30413379]，NeoSphere [PMID:22153890]，KATHERINE [PMID:30516102]，POEMS [PMID:25738668]，ER-low [PMID:37460743]。",
  ].join("\n"));
  slide1.speakerNotes.setVisible(true);

  // ---------- Slide 2: clinical-trial design from governed EDC data ----------
  const slide2 = slideSpec2.slide;
  const title2 = slideSpec2.title;
  title2.text = "案例｜iCore 药物临床试验：EDC 数据治理到 II 期方案设计";
  title2.text.style = { fontSize: 25.5, bold: true, color: NAVY, typeface: CALIBRI };
  const page2 = slideSpec2.page;
  page2.text = "2";
  page2.text.style = { fontSize: 14, bold: true, color: NAVY, typeface: CALIBRI };

  addSurface(slide2, "trial-metric-band", 40, 150, 1200, 92, PANEL, PANEL_LINE);
  const metrics = [
    ["21", "CRF 表单 sheet"],
    ["47,716", "EDC 数据行"],
    ["193", "受试者（100001–100194）"],
    ["20", "同主键 Old/New 并存组"],
    ["46", "II 期计划入组例数"],
  ];
  metrics.forEach((metric, i) => {
    const x = 66 + i * 234;
    addText(slide2, `trial-metric-value-${i + 1}`, x, 168, 205, 30, metric[0], {
      fontSize: 27,
      bold: true,
      color: NAVY,
    });
    addText(slide2, `trial-metric-label-${i + 1}`, x, 203, 205, 24, metric[1], {
      fontSize: 12,
      color: MUTED,
    });
    if (i < metrics.length - 1) addRule(slide2, `trial-metric-split-${i + 1}`, x + 212, 168, 1, "#BFCBD9");
  });

  addSurface(slide2, "trial-governance-panel", 40, 268, 520, 248, "#FFFFFF", PANEL_LINE);
  addText(slide2, "trial-governance-heading", 64, 288, 420, 22, "iCore 数据治理四步", {
    fontSize: 18,
    bold: true,
    color: NAVY,
  });
  addRule(slide2, "trial-governance-rule", 64, 318, 472, "#D6E0F0");
  addText(
    slide2,
    "trial-governance-body",
    64,
    332,
    478,
    166,
    [
      "① 解析与字典：固定 R2 真实表头，建立 21 表变量映射与 schema 断言",
      "② 版本合并：按 Subject/Event/Form Sequence 分组；New 非空优先、Old 回填，并存组输出差异审计",
      "③ 日期与缺失：_DT / _DTF / _RAW 三件套保留部分日期；区分结构性缺失与真缺失",
      "④ 校验交付：完整性、唯一性、一致性、有效性规则；主表 + 宽表/长表 + 可重复流水线",
    ].join("\n"),
    { fontSize: 13.2, color: BODY },
  );

  addSurface(slide2, "trial-protocol-panel", 590, 268, 650, 248, "#FFFFFF", PANEL_LINE);
  addText(slide2, "trial-protocol-heading", 614, 288, 480, 22, "输出的 II 期方案设计", {
    fontSize: 18,
    bold: true,
    color: NAVY,
  });
  addRule(slide2, "trial-protocol-rule", 614, 318, 602, "#D6E0F0");
  addText(
    slide2,
    "trial-protocol-body",
    614,
    332,
    610,
    90,
    [
      "• 研究：不可切除 HCC，Atezolizumab + Bevacizumab 联合 SIRT-Y90；单臂、开放标签 II 期",
      "• 主要终点：ORR（RECIST 1.1）；影像每 8 周评估，生存随访每 12 周",
    ].join("\n"),
    { fontSize: 13.2, color: BODY },
  );
  const simonMetrics = [
    ["p₀ 40%", "不值得继续"],
    ["p₁ 60%", "值得推进"],
    ["17→41", "Simon 两阶段例数"],
    ["80.1%", "把握度（α=0.047）"],
  ];
  simonMetrics.forEach((metric, i) => {
    const x = 614 + i * 152;
    addSurface(slide2, `trial-simon-box-${i + 1}`, x, 436, 140, 56, PANEL, PANEL_LINE);
    addText(slide2, `trial-simon-value-${i + 1}`, x + 12, 446, 116, 20, metric[0], {
      fontSize: 15,
      bold: true,
      color: NAVY,
    });
    addText(slide2, `trial-simon-label-${i + 1}`, x + 12, 469, 116, 18, metric[1], {
      fontSize: 10.5,
      color: MUTED,
    });
  });

  addSurface(slide2, "trial-value-strip", 40, 540, 1200, 72, "#FFFFFF", PANEL_LINE);
  addText(slide2, "trial-value-heading", 64, 554, 220, 22, "治理带来的决策价值", {
    fontSize: 16,
    bold: true,
    color: NAVY,
  });
  addText(
    slide2,
    "trial-value-body",
    300,
    554,
    916,
    46,
    [
      "• 分母锁定：跨 sheet 人群覆盖 32–193 人，合并前明确各分析集，避免重复计数与错误对照",
      "• 可复核：保留原始值、处理规则与差异清单，支持医学监查、query 闭环和后续 SDTM 对齐",
    ].join("\n"),
    { fontSize: 13,
color: BODY },
  );

  addSurface(slide2, "trial-warning-strip", 40, 632, 1200, 34, WARN_BG, WARN_LINE);
  addText(
    slide2,
    "trial-warning-text",
    64,
    639,
    1160,
    22,
    "边界：Old/New 差异清单仍需医学监查确认；方案为草案 v0.1，伦理、注册、申办方授权与监管审批后方可执行。",
    { fontSize: 12, bold: true, color: "#7A4A00" },
  );

  slide2.speakerNotes.textFrame.setText([
    "案例定位：展示 iCore 从 4.77 万行 EDC 导出数据中先治理结构、版本和缺失语义，再把可靠分母与临床背景转化为可讨论的 II 期方案。",
    "数据来源：iCore“数据清洗”项目 data_governance/数据治理方案_AHCC09_Medical_Review.md 与 step1–step5 扫描产物；AHCC09 Medical Review Listings，2026-07-17 快照，21 sheet、47,716 行、193 名受试者。",
    "治理要点：20/21 表含 Status；同主键 Old/New 并存合计 20 组，集中在 Local Labs、Vital Signs、Physical Examination、EGD、Y90 Eligibility、Child-Pugh、HBV/HCV/HIV。日期存在 ISO、DDMMMYYYY 与 YYYY-UN-UN。Y90 Eligibility 95 列中 88 列有缺失，需区分结构性缺失与真缺失。",
    "方案输出：Phase2_Protocol_T+A+SIRT90_HCC_v0.1.md；不可切除 HCC，T+A 联合 SIRT-Y90，单臂 II 期；主要终点 ORR（RECIST 1.1）。Simon Minimax：p0=0.40，p1=0.60，第一阶段 17 例，累计 41 例可评估，r1=7、r=21；α=0.047，power=80.1%，考虑 10% 不可评估率计划入组 46 例。",
    "[Sources] 项目内证据：data_governance/数据治理方案_AHCC09_Medical_Review.md、Phase2_Protocol_T+A+SIRT90_HCC_v0.1.md、step4_deep.txt、step5_overview.txt； 文献：IMbrave150 [PMID:32402160][PMID:34902530]，SARAH post-hoc [PMID:31797680]，Simon two-stage [PMID:2702835]。",
  ].join("\n"));
  slide2.speakerNotes.setVisible(true);

  await fs.mkdir(renderDir, { recursive: true });
  await fs.mkdir(layoutDir, { recursive: true });
  const slides = presentation.slides.items;
  for (let index = 0; index < slides.length; index += 1) {
    const slide = slides[index];
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(renderDir, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 2 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(layoutDir, `${stem}.layout.json`), await layout.text(), "utf8");
  }
  await writeBlob(path.join(renderDir, "deck-montage.webp"), await presentation.export({ format: "webp", montage: true, scale: 1 }));

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(finalPath);
  const stat = await fs.stat(finalPath);
  console.log(JSON.stringify({ finalPath, bytes: stat.size, slides: slides.length }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});

