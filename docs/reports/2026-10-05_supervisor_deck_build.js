// Supervisor update deck: WebGen-Bench long-term memory, 2026-10-05.
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const OUT = process.argv[2];
const THEME = {
  name: "WebGen Memory",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1F2A33", lt1: "FFFFFF", dk2: "0E3B43", lt2: "EEF3F2",
    accent1: "1B998B", accent2: "8C99A6", accent3: "D9534F", accent4: "E59F2F",
    accent5: "2E5266", accent6: "B8D8D3", hlink: "1B998B", folHlink: "2E5266",
  },
};
const HEX = THEME.colors;
const LM = HEX.accent1, NM = HEX.accent2;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "WebGen-Bench 长期记忆 双周汇报";
pres.author = "WebGen Long Memory";
const C = pres.SchemeColor;

const FOOT = "WebGen-Bench 跨任务长期记忆 · 双周汇报 · 2026-10-05";
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.2, w: 11.7, h: 1.6,
      fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.0, w: 11.7, h: 1.4,
      fontSize: 18, color: C.accent6, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.8,
      fontSize: 30, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOT, options: { x: 0.6, y: 7.05, w: 9, h: 0.3, fontSize: 10, color: C.accent2, margin: 0 } } },
  ],
  slideNumber: { x: 12.3, y: 7.05, w: 0.5, h: 0.3, fontSize: 10, color: C.accent2, align: "right" },
});

const content = (section) => pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
const tx = (slide, text, o) => slide.addText(text, { isTextBox: true, margin: 0, fontSize: 14, color: C.text1, ...o });
const card = (slide, x, y, w, h, fill, name) => slide.addShape(pres.shapes.ROUNDED_RECTANGLE,
  { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill }, objectName: name });
const source = (slide, text) => tx(slide, text, { x: 0.6, y: 6.6, w: 12.1, h: 0.35, fontSize: 10, color: C.accent2, italic: true });
const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
  legendFontFace: "+mn-lt", titleFontFace: "+mn-lt", catAxisLabelColor: "1F2A33", valAxisLabelColor: "6B7782",
  dataLabelColor: "1F2A33", catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, dataLabelFontSize: 11 };

// ---------------------------------------------------------------- 1. title
pres.addSection({ title: "开场" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "开场" });
s.addText("跨任务长期记忆能否帮助小模型生成网站？", { placeholder: "title" });
s.addText("WebGen-Bench · 第一阶段结果复盘 + 第二阶段（学校 H200，全自部署）实验设计\n双周汇报 · 2026-10-05", { placeholder: "body" });
s.addNotes("本次汇报三件事：1) 现在用的模型和实验流程；2) 第一阶段（Mac 本地，11 个任务）里 No Memory 的错误类型、Long Memory 如何应对、效果如何；3) 第二阶段在学校 H200 上的完整实验设计和论文主表。第二阶段 11 个任务的试跑已在集群上运行，今天还没有结果。");

// ---------------------------------------------------------------- 2. summary
pres.addSection({ title: "结论" });
s = content("结论");
s.addText("一页结论：有正向信号，但还不能算证据", { placeholder: "title" });
const stats = [
  ["36% → 50%", "检查级准确率\nNo Memory → Long Memory\n第一阶段 8 个共同任务", LM],
  ["5 好 / 3 差", "逐任务比较\nLong Memory 更好 5 个，更差 3 个", HEX.accent5],
  ["28.4%", "论文里 WebGen-LM-7B 准确率\n第二阶段 No Memory 的复现目标", HEX.accent4],
  ["101 × 2", "第二阶段：101 个任务、两组\n11 个任务试跑正在集群上运行", HEX.dk2],
];
stats.forEach(([big, label, color], i) => {
  const x = 0.6 + i * 3.08;
  card(s, x, 1.45, 2.85, 2.55, HEX.lt2, `stat-card-${i + 1}`);
  tx(s, big, { x: x + 0.2, y: 1.6, w: 2.45, h: 0.95, fontSize: 36, bold: true, color: color, fontFace: "Calibri" });
  tx(s, label, { x: x + 0.2, y: 2.6, w: 2.45, h: 1.3, fontSize: 13, color: C.text1, valign: "top" });
});
tx(s, [
  { text: "为什么还不能算证据：", options: { bold: true, breakLine: true } },
  { text: "只有 8 个任务、每组各跑 1 次；Long Memory 链在过程中改过多次方法，混了不同版本的结果。", options: { bullet: true, breakLine: true } },
  { text: "第一阶段的评测流程比论文严（要求 npm run build 通过）、又比论文宽（最多 5 次修复），分数没法和论文对照。", options: { bullet: true, breakLine: true } },
  { text: "第二阶段：全部改用学校 H200 自部署模型 + 论文官方评测协议，重新跑完整 101 个任务。", options: { bullet: true } },
], { x: 0.6, y: 4.3, w: 12.1, h: 2.1, fontSize: 15, valign: "top", paraSpaceAfter: 6 });
s.addNotes("检查级准确率 = (通过 + 0.5×部分通过) / 检查总数，与 WebGen-Bench 官方算法一致。8 个共同任务：014、015、016、017、019、020、021、026（018 的 Long Memory 结果已重置，未计入）。No Memory 15.5/43，Long Memory 21.5/43。");

// ---------------------------------------------------------------- 3. models
pres.addSection({ title: "模型与流程" });
s = content("模型与流程");
s.addText("现在用的模型：尽量贴近论文，只有外观评分不同", { placeholder: "title" });
const head = (t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } });
const rowsModels = [
  [head("角色"), head("论文官方设置"), head("我们（第二阶段，学校 H200）"), head("说明")],
  ["生成网站", "WebGen-LM-7B（Bolt.diy）", "WebGen-LM-7B BF16（vLLM）", "与论文相同"],
  ["功能评测", "WebVoyager + Qwen2.5-VL-32B", "同左，BF16", "与论文相同；647 个测试用例"],
  [{ text: "外观评分", options: { bold: true, color: HEX.accent3 } }, "GPT-4o", "Qwen2.5-VL-32B",
    { text: "唯一偏差：只比较两组，不和论文的 2.5 分比", options: { color: HEX.accent3 } }],
  ["记忆 / 反思", "—（论文没有）", "Qwen2.5-VL-72B（AWQ）", "要看截图；必须和评测模型不同"],
  ["Embedding", "—", "bge-m3", "本地"],
  ["算力", "—", "2 × H200（Slurm 作业）", "不调用任何付费 API"],
];
s.addTable(rowsModels, { x: 0.6, y: 1.4, w: 12.1, colW: [1.7, 3.2, 3.5, 3.7], fontSize: 14, color: HEX.dk1,
  border: { type: "solid", pt: 0.75, color: "D5DDDC" }, rowH: 0.55, valign: "middle", fill: { color: HEX.lt1 } });
source(s, "第一阶段（9 月）：生成器为 Mac 本地 WebGen-LM-7B Q8_0；外观评分、记忆、反思用 Azure GPT-4o / gpt-5.4-mini。两阶段结果不混用。");
s.addNotes("为什么选 WebGen-LM-7B：论文 Bolt.diy 表中能自部署的模型里，Qwen2.5-Coder-32B 只有 9.5%、Qwen2.5-72B 13.8%，接近地板；WebGen-LM-7B 28.4%、14B 29.4%、32B 38.2%，既不贴地板也远离天花板，约 72% 的检查还没通过，记忆有提升空间。7B 速度快，也和第一阶段一致。DeepSeek-V3/R1（671B）和 Claude/GPT 无法自部署。外观评分改用 Qwen2.5-VL-32B：同一作者的 WebGen-Agent 论文在生成循环里就用这个模型给截图打外观分。记忆模型要看截图做外观反思，所以选视觉模型，且与评测模型不同，避免把评分偏好带进记忆。");

// ---------------------------------------------------------------- 4. pipeline diagram
s = content("模型与流程");
s.addText("实验流程：Long Memory 多一个“反思 → 存储 → 检索”循环", { placeholder: "title" });
tx(s, "两组共用（No Memory 只走这一行）", { x: 0.47, y: 1.25, w: 6, h: 0.3, fontSize: 13, bold: true, color: C.accent2 });
const top = [
  ["任务流", "101 个任务\n按 20 个领域分块顺序执行"],
  ["生成网站", "Bolt.diy +\nWebGen-LM-7B"],
  ["启动网站", "npm install + dev server\n（官方协议：不修复）"],
  ["功能评测", "WebVoyager +\nQwen2.5-VL-32B · 647 用例"],
  ["外观评分", "Qwen2.5-VL-32B\n截图 1–5 分"],
];
const bw = 2.2, gap = 0.35, x0 = 0.47, ty = 1.6, th = 1.25;
top.forEach(([t, d], i) => {
  const x = x0 + i * (bw + gap);
  card(s, x, ty, bw, th, HEX.lt2, `flow-shared-${i + 1}`);
  tx(s, [{ text: t, options: { bold: true, fontSize: 15, color: HEX.dk2, breakLine: true } },
         { text: d, options: { fontSize: 12 } }], { x: x + 0.12, y: ty + 0.1, w: bw - 0.24, h: th - 0.2, valign: "middle", align: "center" });
  if (i < top.length - 1) s.addShape(pres.shapes.LINE, { x: x + bw + 0.03, y: ty + th / 2, w: gap - 0.06, h: 0,
    line: { color: HEX.accent2, width: 1.5, endArrowType: "triangle" }, objectName: `arrow-shared-${i + 1}` });
});
card(s, 0.47, 3.75, 12.39, 2.55, "E3F2EF", "lane-longmem");
tx(s, "只有 Long Memory", { x: 0.7, y: 3.85, w: 4, h: 0.3, fontSize: 13, bold: true, color: C.accent1 });
const bottom = [
  { x: 1.75, w: 3.2, t: "下个任务前：检索 + 改写", d: "拆需求 → bge-m3 找相似经验 → 72B 判断是否相关 → 改写成当前任务的做法 → 压缩成至多 6 条" },
  { x: 5.65, w: 2.9, t: "记忆库", d: "具体 case（功能 / 外观）\n全站经验池（次数 × 严重度排序）\n运行统计" },
  { x: 9.25, w: 3.4, t: "任务后反思", d: "Qwen2.5-VL-72B 按 9 步排查：评测员是否到达目标 → 截图 → 代码路径 → 样式追踪 → 结论与可信度" },
];
bottom.forEach((b, i) => {
  card(s, b.x, 4.3, b.w, 1.75, HEX.lt1, `flow-longmem-${i + 1}`);
  tx(s, [{ text: b.t, options: { bold: true, fontSize: 15, color: HEX.dk2, breakLine: true } },
         { text: b.d, options: { fontSize: 12 } }], { x: b.x + 0.15, y: 4.4, w: b.w - 0.3, h: 1.55, valign: "middle" });
});
s.addShape(pres.shapes.LINE, { x: 10.95, y: ty + th + 0.03, w: 0, h: 4.3 - ty - th - 0.06,
  line: { color: HEX.accent1, width: 1.75, endArrowType: "triangle" }, objectName: "arrow-eval-to-reflect" });
tx(s, "评测结果 + 截图 + 代码", { x: 11.05, y: 3.05, w: 1.9, h: 0.55, fontSize: 11, color: C.accent1 });
s.addShape(pres.shapes.LINE, { x: 8.58, y: 5.17, w: 0.64, h: 0, flipH: true,
  line: { color: HEX.accent1, width: 1.75, endArrowType: "triangle" }, objectName: "arrow-reflect-to-store" });
s.addShape(pres.shapes.LINE, { x: 4.98, y: 5.17, w: 0.64, h: 0, flipH: true,
  line: { color: HEX.accent1, width: 1.75, endArrowType: "triangle" }, objectName: "arrow-store-to-retrieve" });
s.addShape(pres.shapes.LINE, { x: 3.35, y: ty + th + 0.03, w: 0, h: 4.3 - ty - th - 0.06, flipV: true,
  line: { color: HEX.accent1, width: 1.75, endArrowType: "triangle" }, objectName: "arrow-inject" });
tx(s, "注入 prompt", { x: 3.45, y: 3.05, w: 1.6, h: 0.3, fontSize: 11, color: C.accent1 });
source(s, "防泄题：检索时排除当前任务自己的记忆；评测结果只用于之后的任务。两组在同一作业里背靠背运行，先后顺序逐任务交替。");
s.addNotes("一次 Slurm 作业占 2 张 H200：第 1 张放生成模型和评测模型，第 2 张放 72B 记忆模型和 embedding。每个任务两组背靠背跑，谁先跑按任务位置交替，避免固定先后带来的偏差。每个任务跑完自动检查评测员是否有回复、外观分能否读出，环境问题会立即停下队列，不会被记成模型失败。");

// ---------------------------------------------------------------- 5. protocol
s = content("模型与流程");
s.addText("评测协议：按论文官方做法，保证 No Memory 能和论文对照", { placeholder: "title" });
const proto = [
  ["任务", "WebGen-Bench 全部 101 个任务、647 个测试用例；按 20 个应用领域分块，同领域的任务连续执行"],
  ["生成", "每个任务只生成一次，不修复，不做我们自己的代码补丁（第一阶段有 build 检查 + 最多 5 次修复，和论文不一致）"],
  ["评测", "依赖装好、dev server 能启动就交给评测员；网站没起来的用例计 0 分，和官方 compute_acc.py 一致"],
  ["指标", "Accuracy = (YES + 0.5 × PARTIAL) / 647；另报 YES / PARTIAL / NO / 未启动比例和外观分（1–5）"],
  ["公平", "两组同一任务背靠背；只排除当前任务自己的记忆；评测结果只用于后续任务，不修当前任务"],
];
proto.forEach(([k, v], i) => {
  const y = 1.45 + i * 1.0;
  card(s, 0.6, y, 1.9, 0.8, i % 2 ? HEX.accent5 : HEX.accent1, `proto-key-${i + 1}`);
  tx(s, k, { x: 0.6, y, w: 1.9, h: 0.8, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
  tx(s, v, { x: 2.8, y, w: 9.9, h: 0.8, fontSize: 15, valign: "middle" });
});
s.addNotes("官方协议的关键差别：Vite 的 dev server 不做类型检查，vue-tsc 的严格类型错误不会阻止网站运行。第一阶段很多“构建失败”在论文的流程里其实能被评测。改为官方协议后，No Memory 的准确率可以直接和论文的 28.4% 对照，作为复现检验。");

// ---------------------------------------------------------------- 6. No Memory errors
pres.addSection({ title: "第一阶段结果" });
s = content("第一阶段结果");
s.addText("No Memory 的错误：43 个检查里 30 个没通过", { placeholder: "title" });
const cats = ["内容缺失或不完整", "功能或版块没做", "构建失败（1 个任务）", "页面写了但没有导航入口", "交互逻辑缺陷", "配色要求没满足", "评测员没给最终结论", "内容看不见（白字 / 空白）"];
const nmCounts = [6, 5, 5, 4, 3, 3, 3, 1];
s.addChart(pres.charts.BAR, [{ name: "No Memory", labels: cats.slice().reverse(), values: nmCounts.slice().reverse() }], {
  x: 0.6, y: 1.35, w: 7.6, h: 5.1, barDir: "bar", chartColors: [NM], showValue: true, dataLabelPosition: "outEnd",
  showLegend: false, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
  valAxisMaxVal: 7, barGapWidthPct: 45, ...chartText, catAxisLabelFontSize: 13 });
card(s, 8.6, 1.45, 4.1, 4.95, HEX.lt2, "nm-error-notes");
tx(s, [
  { text: "怎么读这张图", options: { bold: true, fontSize: 16, color: HEX.dk2, breakLine: true } },
  { text: "检查级准确率 36%（15.5 / 43）", options: { bullet: true, breakLine: true } },
  { text: "前三类都是“网站没把需求做全”：内容不完整、功能没做、页面没入口，合计 15 个", options: { bullet: true, breakLine: true } },
  { text: "构建失败只有 1 个任务（026），但一失败 5 个检查全部记 0", options: { bullet: true, breakLine: true } },
  { text: "“评测员没给结论”不是网站问题：转录在中途结束，被共用解析器记成失败", options: { bullet: true } },
], { x: 8.8, y: 1.6, w: 3.7, h: 4.7, fontSize: 14, valign: "top", paraSpaceAfter: 6 });
source(s, "口径：第一阶段 8 个共同任务（014–017、019–021、026），按评测员最终结论归类，部分经代码核对；交互次数用完的检查按评测员给出的原因归类。");
s.addNotes("分类方法：读每个没通过检查的评测员最终结论，归到 8 类；021 的 4 项“找不到页面”在第一阶段已核对代码，是页面写了却没有导航入口。这是第一阶段数据，第二阶段换了评测协议和浅色模式浏览器，频次会变，届时用反思结果 + 人工抽查重新统计。");

// ---------------------------------------------------------------- 7. how Long Memory addresses them
s = content("第一阶段结果");
s.addText("Long Memory 怎么应对这些错误，效果如何", { placeholder: "title" });
const good = { color: HEX.accent1, bold: true }, bad = { color: HEX.accent3, bold: true }, mid = { color: HEX.accent4, bold: true };
const mech = [
  [head("错误类型"), head("Long Memory 的机制"), head("No Mem → Long Mem"), head("判断")],
  ["构建失败", "失败也写入记忆（“项目要能构建启动”）进全站经验池", "5 → 0", { text: "减少，但只有 1 个任务", options: mid }],
  ["内容缺失或不完整", "按需求功能检索相似 case，改写成当前任务的做法", "6 → 2", { text: "减少", options: good }],
  ["配色要求没满足", "外观 case：背景 / 组件颜色要用到页面上", "3 → 1", { text: "减少", options: good }],
  ["功能或版块没做", "压缩时“只缩不删”，开头和结尾声明需求优先", "5 → 6", { text: "没改善：被压缩掉的功能恰好没做", options: bad }],
  ["页面没有导航入口", "反思判为全站经验，进经验池：“每个版块要有入口”", "4 → 6", { text: "先变坏后修好（见同领域页）", options: mid }],
  ["内容看不见（白字）", "反思追到全局样式表时形成“文字对比度”经验", "1 → 6", { text: "变多：评测环境造成，两组都受影响", options: bad }],
  ["交互逻辑缺陷", "功能 case：提交后要有可见确认", "3 → 4", { text: "没改善", options: bad }],
];
s.addTable(mech, { x: 0.6, y: 1.35, w: 12.1, colW: [2.3, 5.0, 1.9, 2.9], fontSize: 13, color: HEX.dk1,
  border: { type: "solid", pt: 0.75, color: "D5DDDC" }, rowH: 0.56, valign: "middle", fill: { color: HEX.lt1 } });
source(s, "同口径：8 个共同任务、各 43 个检查。“评测员没给结论” 3 → 0 属于评测随机性，未列入。");
s.addNotes("白字问题：Vite 默认 style.css 在深色模式下把文字设成白色，评测浏览器在 Mac 上跟随系统深色模式，白卡片上的文字就看不见。两组都有一半左右的项目引入了这个文件，是否中招有偶然性。第二阶段在 Linux 上评测，浏览器默认浅色模式（已确认），这个问题预计会消失。");

// ---------------------------------------------------------------- 8. overall per task
s = content("第一阶段结果");
s.addText("整体效果：8 个任务里 5 个变好、3 个变差", { placeholder: "title" });
const tasks = ["014", "015", "016", "017", "019", "020", "021", "026"];
s.addChart(pres.charts.BAR, [
  { name: "No Memory", labels: tasks, values: [40, 40, 50, 58, 33, 50, 10, 0] },
  { name: "Long Memory", labels: tasks, values: [60, 100, 17, 33, 42, 40, 80, 40] },
], { x: 0.6, y: 1.35, w: 8.3, h: 5.1, barDir: "col", barGrouping: "clustered", chartColors: [NM, LM],
  showValue: true, dataLabelPosition: "outEnd", showLegend: true, legendPos: "t", legendFontSize: 12,
  valAxisMaxVal: 110, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
  showTitle: true, title: "每个任务的检查级准确率（%）", titleFontSize: 13, titleColor: "1F2A33", barGapWidthPct: 60, ...chartText });
const big = [["36% → 50%", "检查级准确率（共 43 个检查）"], ["2.9 → 3.1", "外观分（1–5，有网站的 7 个任务）"], ["1 → 0", "构建失败的任务数（026）"]];
big.forEach(([b, l], i) => {
  const y = 1.45 + i * 1.65;
  card(s, 9.3, y, 3.4, 1.45, HEX.lt2, `overall-stat-${i + 1}`);
  tx(s, b, { x: 9.5, y: y + 0.12, w: 3.0, h: 0.65, fontSize: 28, bold: true, color: i === 2 ? HEX.accent5 : LM });
  tx(s, l, { x: 9.5, y: y + 0.8, w: 3.0, h: 0.55, fontSize: 12 });
});
source(s, "单次运行；Long Memory 的 014、015 为未压缩旧版，016–021 为 10 月 1 日的几个中间版本，026 为 10 月 2 日版本。");
s.addNotes("第三个数字写法要注意：No Memory 有 1 个任务构建失败（026），Long Memory 没有。变差的 3 个任务原因都已逐项核对：016 guidance 让模型把页面做成独立路由却没有导航入口（0.50→0.17）；017 白字让 3 项内容看不见（0.58→0.33）；020 账户更新与套餐详情没做（0.50→0.40）。");

// ---------------------------------------------------------------- 9. errors reduced?
s = content("第一阶段结果");
s.addText("Long Memory 的错误有没有减少：总数 30 → 25，但结构变了", { placeholder: "title" });
const cmpCats = ["构建失败", "内容缺失或不完整", "配色要求没满足", "评测员没给结论", "功能或版块没做", "交互逻辑缺陷", "页面没有导航入口", "内容看不见（白字）"];
s.addChart(pres.charts.BAR, [
  { name: "No Memory", labels: cmpCats, values: [5, 6, 3, 3, 5, 3, 4, 1] },
  { name: "Long Memory", labels: cmpCats, values: [0, 2, 1, 0, 6, 4, 6, 6] },
], { x: 0.6, y: 1.35, w: 8.6, h: 5.1, barDir: "bar", barGrouping: "clustered", chartColors: [NM, LM],
  showValue: true, dataLabelPosition: "outEnd", showLegend: true, legendPos: "t", legendFontSize: 12,
  valAxisMaxVal: 7, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
  barGapWidthPct: 40, ...chartText, catAxisLabelFontSize: 12, catAxisOrientation: "maxMin" });
card(s, 9.6, 1.45, 3.1, 2.25, "E3F2EF", "fewer-errors");
tx(s, [{ text: "减少了", options: { bold: true, fontSize: 16, color: HEX.accent1, breakLine: true } },
       { text: "构建失败、内容不完整、配色\n——记忆里有对应的具体做法", options: { fontSize: 15 } }],
   { x: 9.8, y: 1.6, w: 2.75, h: 2.0, valign: "top" });
card(s, 9.6, 3.95, 3.1, 2.45, "FBE9E8", "more-errors");
tx(s, [{ text: "变多了", options: { bold: true, fontSize: 16, color: HEX.accent3, breakLine: true } },
       { text: "导航入口：guidance 写“放在单独页面”却没要求入口。\n白字：评测环境造成，和记忆无关", options: { fontSize: 15 } }],
   { x: 9.8, y: 4.1, w: 2.75, h: 2.2, valign: "top" });
source(s, "同口径：8 个共同任务、各 43 个检查。");
s.addNotes("结论：记忆能减少它有具体对策的错误，但也会引入新错误（导航入口），且评测环境噪声（白字）会掩盖真实效果。第二阶段需要在 101 个任务上按同一分类统计，并做多次运行估计方差。");

// ---------------------------------------------------------------- 10. same-domain
s = content("第一阶段结果");
s.addText("同领域实验：重复出现的根因能被修复，但具体经验容易过度迁移", { placeholder: "title" });
tx(s, "领域块 1：Company Brochure Sites（000014–000021，共 8 个任务，连续执行）", { x: 0.6, y: 1.3, w: 12.1, h: 0.35, fontSize: 14, color: C.accent2 });
const steps = [
  ["016", "0.17（No Mem 0.50）", "guidance 让模型建独立页面，但首页没有任何入口，5 项都找不到页面", HEX.accent3],
  ["016 反思", "产出全站经验", "“每个主要版块都要有可点击的导航入口”进入全站经验池", HEX.accent5],
  ["017", "导航检查通过", "通用经验被注入，导航项由部分通过变为通过（但白字让另外 3 项失败）", LM],
  ["018", "0.67 = No Memory", "注入导航 + 文字对比度两条经验；此前同一任务 4 次只有 0.08–0.33", LM],
];
steps.forEach(([t, k, d, color], i) => {
  const x = 0.6 + i * 3.08;
  card(s, x, 1.85, 2.85, 2.55, HEX.lt2, `domain-step-${i + 1}`);
  tx(s, t, { x: x + 0.2, y: 1.97, w: 2.45, h: 0.4, fontSize: 18, bold: true, color: HEX.dk2 });
  tx(s, k, { x: x + 0.2, y: 2.4, w: 2.45, h: 0.45, fontSize: 17, bold: true, color });
  tx(s, d, { x: x + 0.2, y: 2.9, w: 2.45, h: 1.4, fontSize: 14, valign: "top" });
  if (i < steps.length - 1) s.addShape(pres.shapes.LINE, { x: x + 2.88, y: 3.12, w: 0.17, h: 0,
    line: { color: HEX.accent2, width: 1.5, endArrowType: "triangle" }, objectName: `domain-arrow-${i + 1}` });
});
card(s, 0.6, 4.65, 12.1, 1.75, "FBE9E8", "negative-transfer");
tx(s, [{ text: "负迁移的例子", options: { bold: true, fontSize: 15, color: HEX.accent3, breakLine: true } },
       { text: "014 的反思把“交互次数用完”误归因为“服务介绍要放首屏”，加上代码里写死的“首屏展示所有功能”拆解项，被改写成“落地页展示全部内容、不需要导航”：017 改成标签页，018 没有导航。删除写死的拆解项后，导航检查恢复通过。", options: { fontSize: 15 } }],
   { x: 0.85, y: 4.8, w: 11.6, h: 1.5, valign: "top" });
source(s, "领域块 2（Discussion Forums，026–）在第一阶段只跑到 026，样本不足以下结论。");
s.addNotes("同领域确实给了记忆复用的机会：导航入口这类结构性问题在同领域里反复出现（No Memory 021、Long Memory 016），学到后在 017、018 生效。但反思模型较弱时，具体经验会被过度泛化或误归因，带来负迁移。第二阶段 20 个领域块，可以按“在领域块中的位置”统计准确率，直接回答同领域是否解决了问题。");

// ---------------------------------------------------------------- 11. why no stable gain
pres.addSection({ title: "分析" });
s = content("分析");
s.addText("为什么 Long Memory 没有稳定提升", { placeholder: "title" });
const reasons = [
  ["记忆会引入新错误", "guidance 过长时盖过需求（016 只做首页）；列出部分功能时被当成全部范围（018、026 漏做）；写死的设计假设被放大"],
  ["反思模型不够可靠", "只偶尔追到真实根因（白字只追到 1 次）；把猜测标成“确定”；回归集 12–13/18，同一版本两次可以差很多"],
  ["生成器能力上限", "7B 模型拿到“每个版块要有导航”也不总照做；记忆只能提醒，不能补能力"],
  ["评测噪声大于效应", "交互次数用完：No Memory 12/43、Long Memory 19/43 个检查；评测员中途结束；深色模式白字"],
  ["样本小、版本混", "8 个任务、各 1 次；Long Memory 链中途多次改方法；协议与论文不一致"],
];
reasons.forEach(([t, d], i) => {
  const y = 1.4 + i * 1.03;
  s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.08, w: 0.62, h: 0.62, fill: { color: i < 2 ? HEX.accent3 : HEX.accent5 },
    line: { color: i < 2 ? HEX.accent3 : HEX.accent5 }, objectName: `reason-badge-${i + 1}` });
  tx(s, String(i + 1), { x: 0.6, y: y + 0.08, w: 0.62, h: 0.62, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
  tx(s, t, { x: 1.45, y, w: 3.0, h: 0.8, fontSize: 16, bold: true, color: HEX.dk2, valign: "middle" });
  tx(s, d, { x: 4.5, y, w: 8.2, h: 0.8, fontSize: 14, valign: "middle" });
});
s.addNotes("前两条是方法本身的问题，后三条是实验条件的问题。第二阶段针对后三条：官方协议、Linux 浅色模式、101 个任务、冻结方法版本后一次跑完；前两条要靠更强的反思模型（72B）、只缩不删的压缩和后续消融来验证。");

// ---------------------------------------------------------------- 12. ReasoningBank
s = content("分析");
s.addText("ReasoningBank 为什么能提升，我们差在哪", { placeholder: "title" });
const rb = [
  [head("对比项"), head("ReasoningBank（Ouyang 等，2025）"), head("我们（第一阶段）")],
  ["主干模型", "Gemini-2.5-flash / pro、Claude-3.7：能用好抽象策略", "WebGen-LM-7B（8 bit 量化）：不总遵守 guidance"],
  ["任务形态", "多步交互 agent，记忆影响每一步决策", "一次生成整站代码，记忆只在开头注入一次"],
  ["环境重复度", "WebArena 在同几个网站上大量相似任务", "每个任务网站不同；每个领域只有 2–8 个任务"],
  ["记忆内容", "抽象推理策略（标题 / 描述 / 内容），每条轨迹 ≤ 3 条", "具体 case → 改写 → 压缩，最多 6 条"],
  ["注入量", "top-1，很短", "曾达需求原文的 5.7 倍，压缩后约 1.3 倍"],
  ["规模与结果", "数百任务；WebArena 40.5% → 48.8%，加入失败经验 +3.2 点", "8 个任务、单次；36% → 50%，不可靠"],
];
s.addTable(rb, { x: 0.6, y: 1.35, w: 12.1, colW: [2.0, 5.2, 4.9], fontSize: 13, color: HEX.dk1,
  border: { type: "solid", pt: 0.75, color: "D5DDDC" }, rowH: 0.62, valign: "middle", fill: { color: HEX.lt1 } });
tx(s, "可借鉴：更短、更抽象的策略记忆（top-1）；论文主表里加一个 ReasoningBank 式的记忆基线；同领域任务更多时记忆才有机会复用。",
   { x: 0.6, y: 5.9, w: 12.1, h: 0.6, fontSize: 14, bold: true, color: HEX.dk2 });
source(s, "ReasoningBank 数字来自其论文（arXiv 2509.25140）WebArena、Gemini-2.5-flash 设置；失败经验消融为 WebArena-Shopping 46.5% → 49.7%。");
s.addNotes("ReasoningBank：记忆条目由 LLM 从成功和失败轨迹中提炼（成败由 LLM-as-judge 判断，不用标准答案），用 gemini-embedding-001 检索，默认 top-1 注入系统提示，并要求 agent 说明是否采用每条记忆；MaTTS 通过给每个任务更多计算产生更多样的经验来提升记忆质量。我们的差异主要在：模型更弱、任务是一次性生成而非多步交互、同环境任务少、注入更长更具体。");

// ---------------------------------------------------------------- 13. main table design
pres.addSection({ title: "论文设计与下一步" });
s = content("论文设计与下一步");
s.addText("论文主表设计（WebGen-Bench 101 个任务、647 个用例）", { placeholder: "title" });
const mt = [
  [head("方法"), head("准确率"), head("YES"), head("PARTIAL"), head("NO"), head("未启动"), head("外观"), head("功能 / 数据展示 / 设计"), head("注入长度")],
  [{ text: "WebGen-LM-7B（论文报告）", options: { italic: true, color: HEX.accent2, align: "left" } }, "28.4", "24.9", "7.1", "68.0", "—", "2.5*", "—", "—"],
  [{ text: "No Memory（我们复现）", options: { align: "left" } }, "", "", "", "", "", "", "", "0"],
  [{ text: "ReasoningBank 式记忆", options: { align: "left" } }, "", "", "", "", "", "", "", ""],
  [{ text: "Long Memory（ours）", options: { bold: true, color: HEX.accent1, align: "left" } }, "", "", "", "", "", "", "", ""],
  [{ text: "   − 反思排查（只存原始摘要）", options: { align: "left" } }, "", "", "", "", "", "", "", ""],
  [{ text: "   − 压缩（原样注入）", options: { align: "left" } }, "", "", "", "", "", "", "", ""],
  [{ text: "   − 全站经验池", options: { align: "left" } }, "", "", "", "", "", "", "", ""],
];
s.addTable(mt, { x: 0.6, y: 1.35, w: 12.1, colW: [3.3, 1.05, 0.85, 1.05, 0.85, 1.0, 0.85, 2.05, 1.1], fontSize: 13,
  color: HEX.dk1, border: { type: "solid", pt: 0.75, color: "D5DDDC" }, rowH: 0.5, valign: "middle", align: "center", fill: { color: HEX.lt1 } });
tx(s, [
  { text: "配套：", options: { bold: true, breakLine: true } },
  { text: "表 2：错误类型频次（No Memory vs Long Memory），说明哪些错误被记忆减少", options: { bullet: true, breakLine: true } },
  { text: "图：准确率随任务序号的累积曲线，以及按“在领域块中的位置”分组的准确率（回答同领域是否有帮助）", options: { bullet: true, breakLine: true } },
  { text: "每组 ≥ 3 次运行，报均值与按任务配对的置信区间；外观分 * 为 GPT-4o，与我们的 Qwen-VL 分数不可直接比较", options: { bullet: true } },
], { x: 0.6, y: 5.45, w: 12.1, h: 1.15, fontSize: 13, valign: "top" });
s.addNotes("“功能 / 数据展示 / 设计”对应 WebGen-Bench 测试用例的三类：Functional Testing 339、Data Display Testing 186、Design Validation Testing 122。注入长度用来说明长度与效果的关系。若算力允许，再加 WebGen-LM-32B（论文 38.2%）作为第二个生成器，检验结论是否随模型变强而变化。");

// ---------------------------------------------------------------- 14. next steps
s = content("论文设计与下一步");
s.addText("下一步", { placeholder: "title" });
const next = [
  ["进行中", "11 个任务试跑", "核对 No Memory 是否接近 28.4%；检查反思提取、入库、检索是否正常（第 3、5 个任务后各检查一次）"],
  ["约 1–2 天", "全部 101 个任务", "试跑没问题后跑剩下的 90 个；两组同一作业、逐任务交替"],
  ["之后", "基线与消融", "ReasoningBank 式记忆基线；去掉反思排查 / 压缩 / 全站经验池"],
  ["之后", "多次运行", "每组 ≥ 3 次，估计方差；按任务配对比较"],
  ["之后", "错误分析", "按同一分类统计 101 个任务；按领域块位置画学习曲线"],
];
next.forEach(([when, t, d], i) => {
  const y = 1.4 + i * 1.03;
  card(s, 0.6, y, 1.75, 0.82, i === 0 ? HEX.accent1 : HEX.lt2, `next-when-${i + 1}`);
  tx(s, when, { x: 0.6, y, w: 1.75, h: 0.82, fontSize: 14, bold: true, color: i === 0 ? HEX.lt1 : HEX.dk2, align: "center", valign: "middle" });
  tx(s, t, { x: 2.6, y, w: 2.6, h: 0.82, fontSize: 16, bold: true, color: HEX.dk2, valign: "middle" });
  tx(s, d, { x: 5.3, y, w: 7.4, h: 0.82, fontSize: 14, valign: "middle" });
});
s.addNotes("资源：学校 CS ML 集群（8 × H200，Slurm），每个作业 2 张卡、16 核、128GB；不使用 Azure 等付费资源。");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
