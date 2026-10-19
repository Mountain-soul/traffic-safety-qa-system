# 公路交通安全知识图谱与智能问答系统

这是从原工作目录整理出的项目副本。原代码、数据和文档均保留，没有移动或删除。

以后建议用 VS Code 单独打开本文件夹，在这里继续修改和运行，避免与原目录的同名脚本混淆。

## 1. 最常用的入口

| 要做的事 | 文件 |
| --- | --- |
| 启动网页问答 | `qa_web_app.py` |
| 启动终端问答 | `qa_demo.py` |
| 修改问答识别、检索、推理逻辑 | `traffic_qa_engine.py` |
| 将 Excel 数据导入 Neo4j | `import_to_neo4j.py` |
| 批量测试问答 | `batch_test_qa.py` |
| 根据已有数据生成测试问题 | `generate_qa_test_questions.py` |
| 清洗去重、补充来源字段 | `clean_and_source_workbook.py` |

网页的 HTML、CSS、JavaScript 写在 `qa_web_app.py` 中，目前没有单独的前端工程。

## 2. 文件夹结构

```text
交通安全问答系统_整理版/
  README.md                       项目说明，从这里开始
  requirements.txt                Python 依赖
  *.py                            问答、导入、抽取、清洗与历史数据脚本
  run_qa_web.ps1                  网页问答启动脚本
  .vscode/                        本项目专用的调试配置
  data_sources/                   法规及事故报告原文
  generated/                      整理后的数据、测试题和清洗报告
    ppt_images/                   以前的项目展示图片
  docs/                           申请书、检查表、PPT、知识图谱文档
    历史数据/                     早期合并版工作簿
    辅助脚本/                     以前的 PPT 样式处理脚本
```

Python 脚本保留在同一层，`data_sources`、`generated` 保留原名称，避免破坏相互导入和相对路径。

没有收录无关的 MySQL 作业、CPU 报告、储蓄软件、照片设计、可执行文件、缓存和临时目录。旧的压缩材料包未重复打包。

## 3. 怎么启动

先用 VS Code 打开本文件夹，再打开终端。以下命令都在本文件夹根目录执行。

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

先启动你本机的 Neo4j 数据库，再启动网页问答：

```powershell
python qa_web_app.py
```

按提示输入 Neo4j 密码，浏览器访问 `http://127.0.0.1:8000`。密码输入时不显示字符是正常现象。

也可以运行：

```powershell
.\run_qa_web.ps1
```

如果 PowerShell 不允许运行脚本，直接使用上面的 Python 命令即可，不需要更改系统策略。

终端问答：

```powershell
python qa_demo.py
```

这份文件夹不包含 Neo4j 数据库本体或数据库备份。若仍使用原来的本机数据库，无需仅因整理文件而重新导入。

## 4. 当前主要数据

推荐使用：

```text
generated/交通问答系统的数据_清洗溯源版.xlsx
```

其他保留的数据：

- `generated/交通问答系统的数据_第二轮大规模扩充版.xlsx`：前几版扩充数据。
- `generated/qa_test_questions.csv`：已生成的测试问题，不代表所有问题均通过测试。
- `generated/data_quality_cleaning_report.csv`：已有的清洗报告。
- `docs/历史数据/交通问答系统的数据_合并法规版.xlsx`：早期数据，仅作留档。

需要重新导入时运行：

```powershell
python import_to_neo4j.py --xlsx ".\generated\交通问答系统的数据_清洗溯源版.xlsx"
```

该命令不主动清空数据库。整理过程中也没有连接、清空或修改 Neo4j。

## 5. 提取和处理原文

批量提取 DOCX/TXT 法规：

```powershell
python extract_law_documents.py --input data_sources --output generated/extracted_law_articles.csv
```

单独提取单个 DOCX 法规：

```powershell
python extract_law_docx.py --docx "data_sources/中华人民共和国道路交通安全法_20210429.docx" --output generated/road_traffic_safety_law.csv
```

提取事故报告：

```powershell
python extract_accident_documents.py --input data_sources --output generated/extracted_accident_cases.csv
```

事故提取脚本的 DOC/PDF 支持依赖额外工具：PDF 需要 `pdftotext`；DOC 需要 `antiword` 或 LibreOffice 的 `soffice`。这些不是 `pip install -r requirements.txt` 能安装的 Python 包。没有相关工具时，可以先将原文转换为 DOCX/TXT；扫描件需要另做 OCR。

法规与事故提取规则不同。建议将两种原文分别放入 `data_sources` 的子文件夹，并用 `--input` 指定对应子文件夹，避免混用。

提取结果需人工复核，不会自动合并或入库。`merge_law_into_workbook.py` 用于将法规 CSV 合并到已有工作簿，参数可查看：

```powershell
python merge_law_into_workbook.py --help
```

## 6. 测试

```powershell
python generate_qa_test_questions.py
python batch_test_qa.py
```

第二条命令需要 Neo4j 正在运行。结果默认输出到 `generated/qa_test_results.csv`。

当前批量测试的 PASS/CHECK 是脚本的基础判定，不等同于人工核验的答案准确率。

## 7. 历史生成脚本

以下脚本保留供追溯，不是启动系统的必需步骤：

- `generate_violation_penalty_draft.py`：违法处罚草稿。
- `generate_road_sign_draft.py`：道路标志草稿。
- `generate_scoring_method_data.py`：记分管理办法相关预置数据。
- `expand_road_sign_and_accident.py`、`expand_batch2_signs_cases.py`：早期标志和事故案例扩充。
- `expand_full_dataset.py`、`expand_full_dataset_round2.py`：历史批量扩充。

注意：部分扩充脚本通过复制和变换已有记录生成带“扩展”字样的样例，并非联网采集新的真实事故、法规或标志。保留这些脚本和数据用于复现，不代表其中每条记录都已获得权威来源验证；来源字段的存在也不等于内容已核验。

历史脚本的默认输入可能是已经不存在的早期版本。使用前先检查 `--help` 和输入路径，不要为了增加数量直接覆盖当前数据。

## 8. 配置与整理说明

- `.vscode/launch.json` 提供导入、终端问答和网页问答调试入口。
- `.vscode/python.env` 仅含连接地址、用户名和相对数据路径，没有复制真实密码。
- 本机已有的环境变量仍可能覆盖默认配置，切换数据库或数据文件时请检查。
- 整理版 `run_qa_web.ps1` 会先进入自身所在目录，避免从其他目录启动时找不到文件。
- 整理版修正了 `extract_law_documents.py` 的 `--output` 参数的 `defp` 拼写错误及末尾损坏的启动入口；原目录版本未修改。
- `docs/辅助脚本/style_ppt_academic.ps1` 是历史材料工具，默认输出仍含旧路径，使用时需显式指定 `-InputPptx`、`-OutputPptx`。
- 这次整理没有自动执行数据扩充、文档抽取、合并、清洗或数据库导入。
- 整理版与原目录是两份独立副本，后续修改不会自动同步。
