# 医学文献知识库 (knowledge_base)

为《杏林大健康 AI 问答系统》构建的 RAG 起步语料。共收录 **80 篇**文献, 每篇为提取文本(.txt, 头部含标题/作者/期刊卷期/DOI/来源URL),
元数据见 `manifest.jsonl` (标题/作者/期刊/年卷期/DOI/来源URL/文件路径/相关性得分)。
PDF 原文已按要求移除; 如需恢复, 依据 manifest 中的 source_url 重新运行下载脚本即可。

## 各刊收录统计

| 期刊 | 收录篇数 | 说明 |
|---|---|---|
| 中国全科医学 | 34 | OA(2022起), 半月刊, 大众健康+慢病管理相关性最高 |
| 基础医学与临床 | 19 | 官网免费全文, 基础+临床 |
| 精准医学杂志 | 16 | OA(2018起), 双月刊 |
| 临床医药循证研究 | 11 | Gold OA, 2025年创刊 |
| 巴楚医学 | 0 | 2025年起OA, 但门户PDF接口对最新期返回空(跳转知网) |
| 中山大学学报(医学科学版) | 0 | 方正平台 WAF 拦截所有非浏览器客户端(403), 本轮未收录 |

## 主题覆盖分布 (按标题命中疾病统计, 前 30)

- 糖尿病: 13 篇
- 高血压: 12 篇
- 老年: 10 篇
- 儿童: 9 篇
- 肥胖: 9 篇
- 睡眠: 5 篇
- 前列腺: 3 篇
- 前列腺癌: 3 篇
- 结直肠癌: 3 篇
- 肠癌: 3 篇
- 血脂: 3 篇
- 腰椎: 2 篇
- 哮喘: 2 篇
- 卒中: 2 篇
- 关节炎: 2 篇
- 骨关节炎: 2 篇
- 抑郁: 2 篇
- 腰痛: 1 篇
- 痛风: 1 篇
- 高尿酸: 1 篇
- 维生素: 1 篇
- 骨质疏松: 1 篇
- 骨质疏松症: 1 篇
- 胃炎: 1 篇
- 肺炎: 1 篇
- 食管癌: 1 篇
- 乳腺癌: 1 篇
- 癫痫: 1 篇
- 脂肪性肝病: 1 篇
- 焦虑: 1 篇

## 未成功清单

- [no_free_pdf] 巴楚医学 | 儿童糖尿病酮症酸中毒并发症管理的最佳证据总结 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/f74530952ad368bbdefcd86ee798db26
- [no_free_pdf] 巴楚医学 | 脑肠互动障碍及其相关生物-心理-社会因素对肠易激综合征病理生理影响的研究进展 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/993f8dc1e5127e95e5ea0f93bed40ac6
- [no_free_pdf] 巴楚医学 | 成人左心房扩大管理专家共识 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/ed1a462bf76a2ab2d7670cb5aae73622
- [no_free_pdf] 巴楚医学 | 动静脉内瘘成熟机制的研究进展 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/d5b58354f59603acc9ab6139ddf554de
- [no_free_pdf] 巴楚医学 | 新兴治疗靶点mTORC2的作用机制、功能与选择性抑制策略 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/7ce5bb7b9ed91d1c0cb2cf67ac3222dc
- [no_free_pdf] 巴楚医学 | 毒蛇致伤临床诊治专家共识 | https://bmjj.cbpt.cnki.net/portal/journal/portal/client/paper/b69a68518dfad8363db84ca57955eaea

## 扩量方法

```
python download_literature.py --max 300                    # 扩到300篇(自动顺延配额)
python download_literature.py --max 300 --refresh          # 重新抓取候选池(更多年份)
python download_literature.py --journal chinagp,jcyxylc --max 200
```

抓取策略: 仅抓取官网 OA/免费全文, 同站点请求间隔 >=1 秒, 支持断点续传(已成功文章自动跳过)。

## 来源

选题依据《02_医疗文献地址.pdf》所列 6 个 OA 期刊官网; 相关性标准依据《01_需求文档.pdf》
第 8/9 章(18 类固定问答: 疾病-症状/病因/预防/治疗/药品/食品宜忌/检查/并发症等)与 14.8 节医学资料要求。