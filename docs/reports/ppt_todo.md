# 组会 PPT 待更新清单

PPT：https://claude.ai/artifact/4hFFsiPiUgY397YXaZhNqE（幻灯片源文件在 scratchpad `deck/project/`，改完按页重新发布）。
学习曲线脚本：`scripts/plot_learning_curve.py`（输出 `docs/reports/learning_curve_v4_v7.png`，重画后作为新 asset 上传再换 `<img src>`）。

## 阶段 1：v7 跑完 101 题
- [ ] 拉取 `cluster_longmem_v7_webgenlm7b_r1`，重算 No Memory / v4 / v7：前 30、后 71、全部的准确率、外观、零分、检查通过率。
- [ ] `main` 页：换成 101 题数字，去掉"中期结果"脚注；`why` 页：后 71 题的白屏 / 缺 import / prompt 内容统计。
- [ ] `curve` 页：重画学习曲线（101 题）并替换图片。
- [ ] `errors` 页：101 题的零分题分类（No Memory 也为 0 的有几题）、缺 import 题数。
- [ ] **外观核对（用户要求，结果出来再定措辞）：** 只看"两臂网站都能打开"的任务重算外观分；再决定 `conclusion` 页局限写"外观无提升"还是"外观提升主要来自网站能打开"。
- [ ] 正式冻结 v7（DECISIONS），v7 结果即"顺序 1"。

## 阶段 2：消融（只有清单，v7 配置 + 不读写记忆）跑完
- [ ] `abl` 页：填 No Memory / 只有清单 / v7 的前 30、后 71、全部。
- [ ] `conclusion` 页：填"需求拆解贡献 [__]、记忆贡献 [__]"。
- [ ] 若需要，加一张三条线的学习曲线（No Memory / 只有清单 / v7）。

## 阶段 3：顺序实验（种子 11 领域挨着、种子 29 领域打散，Long Memory / No Memory ABBA 交叉执行）跑完
- [ ] `order-1`、`order-2`：每页贴该顺序的 gap 图，填准确率、配对差与 95% bootstrap CI、零分题，标题写一句话结论。
- [ ] `conclusion` 页：填"领域挨着 vs 打散"是否都稳定提升；论文表 tab:order 同步填。
- [ ] `order-design` 页：确认顺序定义与实际执行一致（`data/experiment_splits/task_orders/`）。

## 汇报前
- [ ] 封面：姓名、导师、日期。
- [ ] `refs` 页：逐条核对作者、年份、出处（标"待核对"的）。
